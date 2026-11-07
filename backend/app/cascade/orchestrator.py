"""FastAgent 4-Stage Cascade Orchestrator with Full Security & Safety Hardening."""
import uuid
import time
import hashlib
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from backend.app.cascade.rules import hard_rules_engine
from backend.app.cascade.decision import DecisionModel, LayaDecisionModel, MockDecisionModel, DecisionOutput
from backend.app.llm.base import LLMProvider
from backend.app.llm.mock import MockLLMProvider
from backend.app.policy.engine import PolicyEngine, policy_engine
from backend.app.channels.base import MessagingChannel
from backend.app.channels.mock import MockChannel
from backend.app.tools.base import BaseTool, ToolResult
from backend.app.tools.mock import MockCalendarTool, MockGmailTool
from backend.app.tools.calendar import GoogleCalendarTool
from backend.app.tools.gmail import GmailTool
from backend.app.learning.log import learning_logger
from backend.app.learning.thresholds import threshold_calibrator
from backend.app.learning.retrieval import correction_retriever
from backend.app.metrics import StageTimer, metrics_collector
from backend.app.db.repository import repository, DatabaseRepository
from backend.app.config import settings


class OrchestratorResponse(BaseModel):
    request_id: str
    user_id: str
    intent: str
    risk: str
    confidence: float
    status: str  # direct_rule, executed, pending_confirmation, blocked, failed
    response_text: str
    pending_approval_id: Optional[str] = None
    tool_result: Optional[Dict[str, Any]] = None
    stage_latencies_ms: Dict[str, float] = {}


class CascadeOrchestrator:
    def __init__(
        self,
        decision_model: Optional[DecisionModel] = None,
        llm_provider: Optional[LLMProvider] = None,
        messaging_channel: Optional[MessagingChannel] = None,
        calendar_tool: Optional[BaseTool] = None,
        gmail_tool: Optional[BaseTool] = None,
        db_repo: Optional[DatabaseRepository] = None,
        policy_eng: Optional[PolicyEngine] = None
    ):
        self.decision_model = decision_model or MockDecisionModel()
        if llm_provider:
            self.llm_provider = llm_provider
        elif settings.USE_MOCK_LLM or settings.APP_ENV == "test":
            self.llm_provider = MockLLMProvider()
        elif settings.DEFAULT_LLM_PROVIDER == "meta" and settings.meta_api_key:
            from backend.app.llm.meta import MetaModelProvider
            self.llm_provider = MetaModelProvider()
        elif settings.DEFAULT_LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
            from backend.app.llm.gemini import GeminiProvider
            self.llm_provider = GeminiProvider()
        else:
            self.llm_provider = MockLLMProvider()
        self.messaging_channel = messaging_channel or MockChannel()
        self.calendar_tool = calendar_tool or GoogleCalendarTool()
        self.gmail_tool = gmail_tool or GmailTool()
        self.repo = db_repo or repository
        self.policy_engine = policy_eng or policy_engine
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}

    def _append_history(self, user_id: str, user_msg: str, assistant_msg: str) -> None:
        if not user_id or not user_msg or not assistant_msg:
            return
        history = self.conversation_history.setdefault(user_id, [])
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
        self.conversation_history[user_id] = history[-10:]

    @property
    def pending_approvals(self):
        return self.repo.approvals_store

    def derive_idempotency_key(self, message_id: str, action: str) -> str:
        """Derives a deterministic idempotency key from inbound message_id + action."""
        raw = f"{message_id}:{action}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    async def get_pending_approvals(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.get_user_pending_approvals(user_id)

    async def backdate_approval_for_test(self, approval_id: str, seconds_ago: int = 301):
        rec = await self.repo.get_approval_by_id(approval_id)
        if rec:
            rec["created_at"] = time.time() - seconds_ago
            rec["expires_at"] = rec["created_at"] + 300

    async def handle_message(
        self,
        user_id: str,
        message_text: str,
        source_is_third_party: bool = False,
        inbound_message_id: Optional[str] = None,
        trust_taint: bool = False
    ) -> OrchestratorResponse:
        request_id = str(uuid.uuid4())
        msg_id = inbound_message_id or f"msg_{int(time.time()*1000)}_{str(uuid.uuid4())[:8]}"

        # Fix 8: Deduplicate duplicate webhook deliveries
        if inbound_message_id:
            cached_res = await self.repo.get_webhook_dedupe(inbound_message_id)
            if cached_res:
                return OrchestratorResponse(**cached_res)

        stage_latencies: Dict[str, float] = {}

        # -------------------------------------------------------------
        # Direct Confirmation & Amendment Handling ("yes", "no", corrections)
        # -------------------------------------------------------------
        clean_msg = message_text.strip().lower()
        user_pending = [
            rec for rec in (await self.repo.get_user_pending_approvals(user_id))
            if rec["status"] == "pending"
        ]
        if user_pending:
            latest_approval = user_pending[-1]
            aid = latest_approval["id"]

            if clean_msg in ("yes", "y", "confirm", "haan", "sahi hai"):
                res = await self.resolve_approval(aid, decision="approve", caller_user_id=user_id)
                resp_obj = OrchestratorResponse(
                    request_id=request_id,
                    user_id=user_id,
                    intent=latest_approval["intent"],
                    risk=latest_approval["risk"],
                    confidence=latest_approval["confidence"],
                    status="executed",
                    response_text=res.get("message", res.get("error", "")),
                    tool_result=res.get("tool_result")
                )
                if inbound_message_id:
                    await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
                return resp_obj
            elif clean_msg in ("no", "n", "cancel", "mat karo", "rehne do", "chhod do"):
                res = await self.resolve_approval(aid, decision="reject", caller_user_id=user_id)
                resp_obj = OrchestratorResponse(
                    request_id=request_id,
                    user_id=user_id,
                    intent=latest_approval["intent"],
                    risk=latest_approval["risk"],
                    confidence=latest_approval["confidence"],
                    status="rejected",
                    response_text=res.get("message", "Action cancelled as requested."),
                    tool_result=res.get("tool_result")
                )
                if inbound_message_id:
                    await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
                return resp_obj
            elif (
                clean_msg.startswith(("change ", "make it ", "instead ", "edit ", "set to ", "rather ", "badal do ", "modify ")) or
                clean_msg in ("change", "edit", "modify")
            ):
                from backend.app.cascade.schemas import get_schema_for_intent
                intent_schema = get_schema_for_intent(latest_approval["intent"])
                extract_res = await self.llm_provider.extract_arguments(
                    user_message=f"Original: {latest_approval.get('query_text', '')}. Amendment: {message_text}",
                    intent=latest_approval["intent"],
                    schema=intent_schema
                )
                updated_args = {**(latest_approval.get("arguments") or {})}
                if extract_res.arguments:
                    for k, v in extract_res.arguments.items():
                        if v is not None and v != "":
                            updated_args[k] = v
                res = await self.resolve_approval(aid, decision="edit", caller_user_id=user_id, edited_payload=updated_args)
                preview_lines = []
                for k, v in updated_args.items():
                    if k != "idempotency_key":
                        preview_lines.append(f"- {k.replace('_', ' ').title()}: {v}")
                preview_text = "*Action Updated Preview*\n" + "\n".join(preview_lines) + "\n\nReply *CONFIRM* to execute or *CANCEL* to discard."
                await self.messaging_channel.send_text(user_id, preview_text)
                resp_obj = OrchestratorResponse(
                    request_id=request_id,
                    user_id=user_id,
                    intent=latest_approval["intent"],
                    risk=latest_approval["risk"],
                    confidence=latest_approval["confidence"],
                    status="pending_confirmation",
                    response_text=preview_text
                )
                if inbound_message_id:
                    await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
                return resp_obj

        # -------------------------------------------------------------
        # STAGE 1: Hard Rules in Code (<1ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        with StageTimer("stage_1_rules"):
            rule_res = hard_rules_engine.evaluate(message_text)
        stage_latencies["stage_1_rules"] = (time.perf_counter() - t0) * 1000

        if rule_res.matched:
            metrics_collector.record_intent("rule_direct")
            metrics_collector.record_token_savings(len(message_text))

            resp_text = rule_res.direct_response or ""
            # Fix 5: Emergency stop cancels all user pending approvals and states count
            if rule_res.action_override == "halt_all":
                cancelled_count = await self.repo.cancel_user_pending_approvals(user_id)
                resp_text = f"All automated actions halted. {cancelled_count} pending approval(s) were cancelled."

            resp_obj = OrchestratorResponse(
                request_id=request_id,
                user_id=user_id,
                intent="rule_direct",
                risk="low",
                confidence=1.0,
                status="direct_rule",
                response_text=resp_text,
                stage_latencies_ms=stage_latencies
            )
            await self.repo.insert_audit_log({
                "request_id": request_id,
                "user_id": user_id,
                "raw_intent": "rule_direct",
                "risk_level": "low",
                "confidence": 1.0,
                "tools_called": [],
                "was_confirmed": False,
                "status": "direct_rule",
                "stage_latencies_ms": stage_latencies
            })
            if inbound_message_id:
                await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
            return resp_obj

        # -------------------------------------------------------------
        # STAGE 2: Fast Decision Layer (Laya System 1) (<30ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        with StageTimer("stage_2_laya_decision"):
            decision = await self.decision_model.decide(message_text)
        stage_latencies["stage_2_laya_decision"] = (time.perf_counter() - t0) * 1000
        metrics_collector.record_intent(decision.intent)

        # -------------------------------------------------------------
        # STAGE 3: Targeted LLM Argument Extraction & 'other' / Skills
        # -------------------------------------------------------------
        extracted_args: Dict[str, Any] = {}
        t0 = time.perf_counter()

        # Fix 9: "other" intent goes to dynamic skills or LLM conversational reply (unless trust-tainted or third-party)
        if decision.intent == "other" and not trust_taint and not source_is_third_party:
            # Check for matching custom or global agent skill
            matching_skill = await self.repo.find_matching_skill(user_id, message_text)
            if matching_skill:
                t_skill = time.perf_counter()
                skill_name = matching_skill.get("name", "Custom Skill")
                system_prompt = matching_skill.get("system_prompt", "")
                webhook_url = matching_skill.get("webhook_url")

                skill_reply = ""
                if webhook_url:
                    try:
                        import httpx
                        from urllib.parse import urlparse
                        import ipaddress
                        
                        parsed = urlparse(webhook_url)
                        is_safe = parsed.scheme == "https" and parsed.hostname
                        if is_safe:
                            import socket
                            # Resolve DNS at request time to prevent DNS rebinding to internal/private IPs
                            try:
                                resolved_info = socket.getaddrinfo(parsed.hostname, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
                                for _, _, _, _, sockaddr in resolved_info:
                                    ip_obj = ipaddress.ip_address(sockaddr[0])
                                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
                                        is_safe = False
                                        break
                            except Exception:
                                is_safe = False
                        
                        if is_safe:
                            # follow_redirects=False prevents open redirect SSRF bypasses
                            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                                resp = await client.post(
                                    webhook_url,
                                    json={
                                        "user_id": user_id,
                                        "message": message_text,
                                        "skill_name": skill_name
                                    }
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    skill_reply = data.get("response") or data.get("reply") or str(data)
                        else:
                            skill_reply = "Skill webhook blocked due to invalid or unsafe destination URL."
                    except Exception:
                        skill_reply = "Error communicating with skill webhook service."

                if not skill_reply:
                    history = self.conversation_history.get(user_id, [])
                    skill_reply = await self.llm_provider.generate_response(
                        system_prompt=system_prompt,
                        user_message=message_text,
                        context={"user_id": user_id, "skill": matching_skill, "history": history[-8:]}
                    )
                self._append_history(user_id, message_text, skill_reply)

                stage_latencies["skill_execution"] = (time.perf_counter() - t_skill) * 1000
                await self.messaging_channel.send_text(user_id, skill_reply)

                resp_obj = OrchestratorResponse(
                    request_id=request_id,
                    user_id=user_id,
                    intent=f"skill_{matching_skill.get('slug', 'custom')}",
                    risk="low",
                    confidence=1.0,
                    status="executed",
                    response_text=skill_reply,
                    stage_latencies_ms=stage_latencies
                )
                await self.repo.insert_audit_log({
                    "request_id": request_id,
                    "user_id": user_id,
                    "raw_intent": f"skill_{matching_skill.get('slug', 'custom')}",
                    "risk_level": "low",
                    "confidence": 1.0,
                    "tools_called": [f"skill:{skill_name}"],
                    "was_confirmed": False,
                    "status": "executed",
                    "stage_latencies_ms": stage_latencies
                })
                if inbound_message_id:
                    await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
                return resp_obj

            with StageTimer("stage_3_llm_extraction"):
                llm_res = await self.llm_provider.extract_arguments(
                    user_message=message_text,
                    intent="other",
                    schema={}
                )
                system_prompt = (
                    "You are DUIT, an intelligent, natural, and highly capable personal AI Chief of Staff. "
                    "The user interacts with you through WhatsApp text or voice messages. "
                    "Speak naturally, helpfully, and conversationally like a trusted personal assistant (similar to Meta AI or ChatGPT). "
                    "Keep responses concise, clear, and direct. Strictly zero emojis. "
                    "You have direct intelligence capabilities: you can securely read, search, and summarize incoming WhatsApp conversations, "
                    "manage Google Calendar & Gmail, launch and control applications on the user's desktop, "
                    "and organize tasks. When asked about reading WhatsApp messages, confirm that you securely archive and can search/summarize "
                    "their messages and commitments whenever asked."
                )
                # Real-time user profile and connection awareness
                google_tokens = await self.repo.get_user_oauth_tokens(user_id, "google")
                has_google = bool(google_tokens and (google_tokens.get("access_token") or google_tokens.get("encrypted_access_token")))

                from backend.app.desktop.presence import presence_manager
                is_desktop = presence_manager.is_online(user_id)

                system_prompt += (
                    f"\n\n[Real-time User Connection Status]\n"
                    f"- User Phone: {user_id}\n"
                    f"- WhatsApp Interface: Live and Active (the user is currently messaging you here)\n"
                    f"- Google Services (Gmail & Calendar): {'Connected' if has_google else 'Not connected yet'}\n"
                    f"- Workstation / Desktop: {'Online' if is_desktop else 'Offline'}\n"
                    f"Rules for answering status and capabilities:\n"
                    f"1. When the user asks about WhatsApp messages or chats, remember their WhatsApp is ALREADY live and connected. Do not ask them to connect Google unless they explicitly mention Gmail or Google Calendar.\n"
                    f"2. When the user asks 'are my services connected' or checks status, report the exact status above accurately.\n"
                    f"3. If the user corrects you or mentions 'not google', acknowledge smoothly and focus on their specific request.\n"
                )

                history = self.conversation_history.get(user_id, [])
                try:
                    conversational_reply = await self.llm_provider.generate_response(
                        system_prompt=system_prompt,
                        user_message=message_text,
                        context={"history": history[-8:]}
                    )
                except Exception:
                    conversational_reply = "I hear you, but my AI language model provider is currently experiencing downtime. No action was taken. Please try again in a moment."
                self._append_history(user_id, message_text, conversational_reply)
            stage_latencies["stage_3_llm_extraction"] = (time.perf_counter() - t0) * 1000
            await self.messaging_channel.send_text(user_id, conversational_reply)

            resp_obj = OrchestratorResponse(
                request_id=request_id,
                user_id=user_id,
                intent="other",
                risk="low",
                confidence=decision.confidence,
                status="executed",
                response_text=conversational_reply,
                stage_latencies_ms=stage_latencies
            )
            if inbound_message_id:
                await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
            return resp_obj

        # Extract arguments for both write AND read intents (Fix 9: read intents run argument extraction)
        with StageTimer("stage_3_llm_extraction"):
            from backend.app.cascade.schemas import get_schema_for_intent
            intent_schema = get_schema_for_intent(decision.intent)
            llm_res = await self.llm_provider.extract_arguments(
                user_message=message_text,
                intent=decision.intent,
                schema=intent_schema
            )
            extracted_args = llm_res.arguments or {}
            extracted_args.setdefault("query_text", message_text)
        stage_latencies["stage_3_llm_extraction"] = (time.perf_counter() - t0) * 1000

        # -------------------------------------------------------------
        # Cross-Channel Desktop Target Presence Check (<1ms)
        # -------------------------------------------------------------
        desktop_intents = {"open_app", "open_url", "create_note", "type_text", "set_volume", "search_files", "clear_history"}
        if decision.intent in desktop_intents:
            from backend.app.desktop.presence import presence_manager
            if not presence_manager.is_online(user_id):
                offline_reply = "laptop offline"
                await self.messaging_channel.send_text(user_id, offline_reply)
                resp_obj = OrchestratorResponse(
                    request_id=request_id,
                    user_id=user_id,
                    intent=decision.intent,
                    risk="low",
                    confidence=decision.confidence,
                    status="offline",
                    response_text=offline_reply,
                    stage_latencies_ms=stage_latencies
                )
                if inbound_message_id:
                    await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
                return resp_obj

        # -------------------------------------------------------------
        # STAGE 4: Policy Engine & Approvals Validation (<2ms)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        with StageTimer("stage_4_policy_engine"):
            auto_thresh = threshold_calibrator.calculate_threshold(user_id, decision.intent)
            policy_eval = self.policy_engine.evaluate_action(
                user_id=user_id,
                intent=decision.intent,
                arguments=extracted_args,
                confidence=decision.confidence,
                source_is_third_party=source_is_third_party,
                trust_taint=trust_taint,
                auto_approve_threshold=auto_thresh
            )
        stage_latencies["stage_4_policy_engine"] = (time.perf_counter() - t0) * 1000

        if not policy_eval.allowed:
            resp_obj = OrchestratorResponse(
                request_id=request_id,
                user_id=user_id,
                intent=decision.intent,
                risk=policy_eval.risk_level,
                confidence=decision.confidence,
                status="blocked",
                response_text=f"Action blocked by policy: {policy_eval.reasoning}",
                stage_latencies_ms=stage_latencies
            )
            if inbound_message_id:
                await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
            return resp_obj

        # Fix 8: Idempotency key derived from message_id + action
        idempotency_key = self.derive_idempotency_key(msg_id, decision.intent)
        extracted_args["idempotency_key"] = idempotency_key

        # -------------------------------------------------------------
        # Confirmation Gate
        # -------------------------------------------------------------
        if policy_eval.requires_confirmation:
            # Fix 2 & 7: Store in DB repository with 1 active pending per user & 5m expiry
            approval_rec = await self.repo.create_pending_approval(
                user_id=user_id,
                request_id=request_id,
                query_text=message_text,
                intent=decision.intent,
                risk=policy_eval.risk_level,
                confidence=decision.confidence,
                arguments=extracted_args,
                expires_in_seconds=300  # 5 minutes
            )
            approval_id = approval_rec["id"]

            prompt = policy_eval.suggested_prompt or f"Should I proceed with {decision.intent}?"
            await self.messaging_channel.send_confirmation_prompt(
                recipient=user_id,
                text=prompt,
                action_id=approval_id
            )

            await self.repo.insert_audit_log({
                "request_id": request_id,
                "user_id": user_id,
                "raw_intent": decision.intent,
                "risk_level": policy_eval.risk_level,
                "confidence": decision.confidence,
                "tools_called": [],
                "was_confirmed": False,
                "status": "pending_confirmation",
                "stage_latencies_ms": stage_latencies
            })

            resp_obj = OrchestratorResponse(
                request_id=request_id,
                user_id=user_id,
                intent=decision.intent,
                risk=policy_eval.risk_level,
                confidence=decision.confidence,
                status="pending_confirmation",
                response_text=prompt,
                pending_approval_id=approval_id,
                stage_latencies_ms=stage_latencies
            )
            if inbound_message_id:
                await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
            return resp_obj

        # -------------------------------------------------------------
        # Direct Tool Execution (Read queries or auto-approved)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        with StageTimer("stage_5_tool_execution"):
            tool_res = await self._execute_tool(user_id, decision.intent, extracted_args)
        stage_latencies["stage_5_tool_execution"] = (time.perf_counter() - t0) * 1000

        if not tool_res.success:
            reply_msg = f"Failed to execute action: {tool_res.error}"
        elif decision.intent == "whatsapp_search":
            summary_data = tool_res.data or {}
            reply_msg = summary_data.get(
                "summary_text",
                "I searched your archived WhatsApp history. No recorded messages were found matching your criteria in this window."
            )
        elif decision.intent == "summarize_email":
            emails = (tool_res.data or {}).get("emails", [])
            snippets = (tool_res.data or {}).get("snippets", [])
            if emails:
                lines = []
                has_urgent = any("urgent" in (e.get("subject", "") + e.get("snippet", "")).lower() for e in emails)
                urgency = "High (Action Required)" if has_urgent else "Low (Promotional, Notifications & Job Alerts)"
                
                lines.append(f"*Email Briefing Summary ({len(emails)} Recent Messages)*")
                lines.append(f"- Total New Emails: {len(emails)}")
                lines.append(f"- Urgency Level: {urgency}\n")
                lines.append("*Email Breakdown:*")

                import re
                for i, em in enumerate(emails, 1):
                    sender = em.get("from", "Unknown")
                    sender_name = sender.split("<")[0].strip().strip('"') if "<" in sender else sender
                    sender_name = re.sub(r'[\u200b-\u200f\ufeff\xad]', '', sender_name).strip()
                    subject = re.sub(r'[\u200b-\u200f\ufeff\xad]', '', em.get("subject", "No Subject")).strip()
                    snip = re.sub(r'[\u200b-\u200f\ufeff\xad]', '', em.get("snippet", "")).strip()
                    
                    short_snip = snip.split(".")[0].strip() if "." in snip else snip[:120]
                    if not short_snip:
                        short_snip = "No preview available"

                    sub_lower = (subject + " " + snip).lower()
                    if any(k in sub_lower for k in ("job", "hiring", "intern", "career", "manager")):
                        tag = "Job Alert"
                    elif any(k in sub_lower for k in ("insurance", "offer", "deal", "discount", "sale", "trip")):
                        tag = "Promotion/Offer"
                    elif any(k in sub_lower for k in ("account", "security", "update", "verify", "password")):
                        tag = "Account/Security"
                    else:
                        tag = "General"

                    lines.append(f"{i}. *{sender_name}* | {subject}\n   [{tag}] {short_snip}.")

                lines.append("\n*Takeaway:* Routine promotional & alert notifications. No critical action required.")
                reply_msg = re.sub(r'[\u200b-\u200f\ufeff\xad]', '', "\n".join(lines))
            elif snippets:
                lines = ["*Email Briefing Summary:*"]
                for i, snip in enumerate(snippets, 1):
                    lines.append(f"{i}. {snip}")
                reply_msg = "\n".join(lines)
            else:
                reply_msg = "No recent emails found in your inbox."
        elif decision.intent == "check_calendar":
            events = (tool_res.data or {}).get("events", [])
            if events:
                lines = ["Your upcoming calendar events:"]
                for i, ev in enumerate(events[:5], 1):
                    title = ev.get("summary", "Meeting")
                    start = ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date") or "TBD"
                    lines.append(f"{i}. {title} ({start})")
                reply_msg = "\n".join(lines)
            else:
                reply_msg = "Your calendar is clear. No upcoming events found."
        elif decision.intent == "search_files":
            matches = (tool_res.data or {}).get("matches", [])
            file_contents = (tool_res.data or {}).get("file_contents", {})
            tool_msg = (tool_res.data or {}).get("message", "")
            query = extracted_args.get("query", "files")
            if tool_msg and "Read '" in tool_msg:
                reply_msg = tool_msg
            elif file_contents:
                first_f, first_c = next(iter(file_contents.items()))
                reply_msg = f"Read '{first_f}':\n\n{first_c}"
            elif matches:
                lines = [f"Found {len(matches)} file(s) matching '{query}':"]
                import os
                for i, m in enumerate(matches[:5], 1):
                    lines.append(f"- {os.path.basename(m)}")
                reply_msg = "\n".join(lines)
            else:
                reply_msg = f"No files found matching '{query}' on your desktop."
        elif decision.intent == "shed_status":
            status_data = (tool_res.data or {}).get("shed_status", {})
            online = status_data.get("online", False)
            url = status_data.get("url", "http://127.0.0.1:4378")
            if not online:
                reply_msg = f"*Shed Task Plane Status: Offline*\nNotice: {status_data.get('notice', 'Server offline.')}"
            else:
                harnesses = status_data.get("harnesses", {})
                h_lines = []
                for h_name, h_info in harnesses.items():
                    installed = h_info.get("installed", False)
                    state = "Ready" if installed else "Not installed"
                    h_lines.append(f"- {h_name.capitalize()}: {state}")
                harness_summary = "\n".join(h_lines) if h_lines else "- No harnesses registered"
                active_count = status_data.get("active_sessions_count", 0)
                reply_msg = (
                    f"*Shed Task Plane Status: Online*\n"
                    f"- URL: {url}\n"
                    f"- Active Coding Sessions: {active_count}\n\n"
                    f"*Available Harnesses:*\n"
                    f"{harness_summary}\n\n"
                    f"Send 'start coding <prompt>' to dispatch a task."
                )
        elif decision.intent == "dispatch_coding_task":
            task_info = tool_res.data or {}
            task_id = task_info.get("id", "queued")
            harness_used = task_info.get("harness", "agent")
            title = task_info.get("title", "Coding task")
            status = task_info.get("status", "running")
            reply_msg = (
                f"*Shed Coding Task Dispatched*\n"
                f"- Task ID: {task_id}\n"
                f"- Harness: {harness_used}\n"
                f"- Title: {title}\n"
                f"- Status: {status}\n\n"
                f"Agent is now executing on your workstation."
            )
        elif decision.intent == "automate_cart":
            cart_info = tool_res.data or {}
            store = cart_info.get("store", "Amazon")
            product = cart_info.get("product", "Item")
            status = cart_info.get("status", "Added to Cart")
            url = cart_info.get("url", "")
            reply_msg = (
                f"*Cart Automation: {status}*\n"
                f"- Store: {store}\n"
                f"- Product: {product}\n"
                + (f"- Link: {url}\n" if url else "")
                + "The item has been added to your shopping cart."
            )
        elif tool_res.data and "message" in tool_res.data:
            reply_msg = str(tool_res.data["message"])
        elif tool_res.data and "output" in tool_res.data:
            reply_msg = str(tool_res.data["output"])
        else:
            reply_msg = f"Done! Executed {decision.intent}."

        await self.messaging_channel.send_text(user_id, reply_msg)
        self._append_history(user_id, message_text, reply_msg)

        await self.repo.insert_audit_log({
            "request_id": request_id,
            "user_id": user_id,
            "raw_intent": decision.intent,
            "risk_level": policy_eval.risk_level,
            "confidence": decision.confidence,
            "tools_called": [decision.intent],
            "was_confirmed": False,
            "status": "executed" if tool_res.success else "failed",
            "stage_latencies_ms": stage_latencies
        })

        resp_obj = OrchestratorResponse(
            request_id=request_id,
            user_id=user_id,
            intent=decision.intent,
            risk=policy_eval.risk_level,
            confidence=decision.confidence,
            status="executed" if tool_res.success else "failed",
            response_text=reply_msg,
            tool_result=tool_res.data,
            stage_latencies_ms=stage_latencies
        )
        if inbound_message_id:
            await self.repo.save_webhook_dedupe(inbound_message_id, resp_obj.model_dump())
        return resp_obj

    async def _execute_tool(self, user_id: str, intent: str, args: Dict[str, Any]) -> ToolResult:
        if intent in ("schedule_meeting", "reschedule_meeting", "cancel_meeting", "check_calendar"):
            act = intent.replace("_meeting", "").replace("check_", "list")
            args["action"] = "create" if act == "schedule" else act
            return await self.calendar_tool.execute(user_id, args)
        elif intent in ("send_email", "reply_email", "summarize_email"):
            args["action"] = "send" if intent in ("send_email", "reply_email") else "summarize"
            return await self.gmail_tool.execute(user_id, args)
        elif intent == "whatsapp_search":
            user = await self.repo.get_user(user_id)
            tenant_id = user.get("tenant_id", "tenant_default") if user else "tenant_default"
            account = await self.repo.get_user_whatsapp_account(user_id, tenant_id=tenant_id)
            if not account and user:
                account = await self.repo.link_whatsapp_account(
                    tenant_id=tenant_id,
                    user_id=user["id"],
                    phone_number=user.get("phone_number", user_id),
                    display_name=user.get("display_name", user_id)
                )
            if not account:
                return ToolResult(
                    success=False,
                    error="No linked WhatsApp account found for this user."
                )

            account_id = account["id"]
            query = args.get("query") or args.get("query_text")
            contact = args.get("contact") or args.get("sender_phone")
            limit = int(args.get("limit", 10))

            summary_res = await self.repo.generate_archive_summary(
                tenant_id=tenant_id,
                whatsapp_account_id=account_id,
                query_text=query if query and query.strip().lower() != user_id.lower() else None,
                contact=contact,
                limit=limit
            )
            return ToolResult(
                success=True,
                data=summary_res
            )
        elif intent == "book_something":
            return ToolResult(
                success=False,
                error="Live booking integration is currently under development. No booking was created."
            )
        elif intent == "shed_status":
            from backend.app.desktop.shed_bridge import shed_bridge
            status = await shed_bridge.get_status()
            return ToolResult(success=True, data={"shed_status": status})
        elif intent == "dispatch_coding_task":
            from backend.app.desktop.shed_bridge import shed_bridge
            prompt = args.get("prompt", "")
            harness = args.get("harness", "auto")
            res = await shed_bridge.dispatch_task(prompt=prompt, harness=harness)
            return ToolResult(success=res.get("success", False), data=res.get("task", {}), error=res.get("error"))
        elif intent in ("open_app", "open_url", "create_note", "type_text", "set_volume", "search_files", "clear_history", "automate_cart", "generate_briefing_pdf", "briefing_pdf", "generate_pdf"):
            from backend.app.desktop.presence import presence_manager
            from backend.app.desktop.skills import skill_executor
            if presence_manager.is_online(user_id):
                res = await presence_manager.send_command_to_desktop(
                    user_id=user_id,
                    command_payload={"intent": intent, "arguments": args}
                )
                return ToolResult(
                    success=res.get("success", False),
                    data=res.get("result", res),
                    error=res.get("error")
                )
            else:
                try:
                    res = skill_executor.execute_skill(intent, args)
                    return ToolResult(success=True, data=res)
                except Exception as e:
                    return ToolResult(success=False, error=str(e))
        else:
            # Fix 9: Unimplemented tools return explicit error result, never fake success
            return ToolResult(
                success=False,
                error=f"Tool not supported: Action '{intent}' has no implemented tool adapter."
            )

    async def resolve_approval(
        self,
        approval_id: str,
        decision: str,  # approve, edit, reject
        caller_user_id: str,
        edited_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        # Fix 2: Caller validation, status check, 5-minute expiry
        rec = await self.repo.get_approval_by_id(approval_id)
        if not rec:
            return {"error": "Approval request not found"}

        if rec["user_id"] != caller_user_id:
            return {"error": "Unauthorized: caller does not own this approval"}

        if rec["status"] == "expired":
            return {"error": "Approval request has expired (5-minute limit)"}

        if rec["status"] != "pending":
            return {"error": f"Approval is not pending (current status: {rec['status']})"}

        user_id = rec["user_id"]
        orig_idempotency_key = rec["arguments"].get("idempotency_key")

        # Fix 2: Edits re-run the policy engine and keep original idempotency key
        if decision == "edit" and edited_payload:
            edited_payload["idempotency_key"] = orig_idempotency_key
            rec["arguments"].update(edited_payload)

            # Re-evaluate policy engine on edited payload
            policy_eval = self.policy_engine.evaluate_action(
                user_id=user_id,
                intent=rec["intent"],
                arguments=rec["arguments"],
                confidence=rec["confidence"]
            )

            learning_logger.log_correction(
                user_id=user_id,
                query_text=rec["query_text"],
                predicted_intent=rec["intent"],
                user_action="edit",
                corrected_payload=edited_payload
            )

            if policy_eval.requires_confirmation:
                # Keep approval pending with updated arguments
                msg = f"Updated action still requires confirmation: {policy_eval.reasoning}"
                await self.messaging_channel.send_text(user_id, msg)
                return {"status": "edited_held", "message": msg, "record": rec}
            else:
                # Allowed to execute
                tool_res = await self._execute_tool(user_id, rec["intent"], rec["arguments"])
                rec["status"] = "edited"
                rec["resolved_at"] = time.time()
                msg = "Action updated and executed with your corrections."
                await self.messaging_channel.send_text(user_id, msg)
                return {"status": "edited", "message": msg, "tool_result": tool_res.data}

        # Resolve through repository
        resolve_res = await self.repo.resolve_approval(
            approval_id=approval_id,
            decision=decision,
            caller_user_id=caller_user_id
        )
        if "error" in resolve_res:
            return resolve_res

        # Log explicit user action to continuous learning dataset
        learning_logger.log_correction(
            user_id=user_id,
            query_text=rec["query_text"],
            predicted_intent=rec["intent"],
            user_action=decision,
            corrected_payload=edited_payload
        )

        if decision == "approve":
            tool_res = await self._execute_tool(user_id, rec["intent"], rec["arguments"])
            if not tool_res.success:
                msg = f"Could not complete action:\n\n{tool_res.error or 'Tool execution failed'}"
                await self.messaging_channel.send_text(user_id, msg)
                return {"status": "failed", "message": msg, "error": tool_res.error}

            title = rec["arguments"].get("title", "Meeting")
            start = rec["arguments"].get("start_time", "")
            end = rec["arguments"].get("end_time", "")
            time_part = f"{start} to {end}" if end else start

            if rec["intent"] in ("schedule_meeting", "create_calendar_event"):
                msg = f"*Action confirmed & scheduled!*\n\n*{title}*\n*Time:* {time_part}"
                if tool_res.data and tool_res.data.get("html_link"):
                    msg += f"\nCalendar Link: {tool_res.data.get('html_link')}"
                else:
                    msg += f"\nAdded to your Google Calendar."
            elif rec["intent"] in ("send_email", "reply_email"):
                recip = rec["arguments"].get("recipient", "")
                subj = rec["arguments"].get("subject", "")
                msg = f"*Action confirmed & email sent!*\n\n*To:* {recip}\n*Subject:* {subj}"
            elif rec["intent"] == "open_app":
                app_name = rec["arguments"].get("app_name", "application")
                if tool_res.data and tool_res.data.get("message"):
                    msg = f"*Action confirmed!*\n{tool_res.data['message']}"
                else:
                    msg = f"*Action confirmed! Opened {app_name} on your desktop.*"
            elif rec["intent"] == "open_url":
                url = rec["arguments"].get("url", "website")
                if tool_res.data and tool_res.data.get("message"):
                    msg = f"*Action confirmed!*\n{tool_res.data['message']}"
                else:
                    msg = f"*Action confirmed! Opened {url} in your desktop browser.*"
            elif rec["intent"] == "type_text":
                count = (tool_res.data or {}).get("character_count", len(rec["arguments"].get("text", "")))
                msg = f"*Action confirmed! Typed text into your active desktop window ({count} characters).*"
            elif rec["intent"] == "create_note":
                title = rec["arguments"].get("title", "Note")
                msg = f"*Action confirmed! Created note '{title}' on your desktop.*"
            elif rec["intent"] == "search_files":
                query = rec["arguments"].get("query", "files")
                count = (tool_res.data or {}).get("count", 0)
                msg = f"*Action confirmed! Searched for '{query}' on your desktop ({count} match(es) found).*"
            elif rec["intent"] == "dispatch_coding_task":
                task_data = tool_res.data or {}
                harness = task_data.get("harness", "agent")
                task_id = task_data.get("id", "queued")
                msg = f"*Action confirmed! Dispatched coding task to Shed ({harness})*\nTask ID: {task_id}\nAgent is executing."
            elif rec["intent"] == "automate_cart":
                product = rec["arguments"].get("product_name", "item")
                store = rec["arguments"].get("store", "Amazon")
                url = (tool_res.data or {}).get("url", "")
                link_part = f"\nLink: {url}" if url else ""
                msg = f"*Action confirmed! Searched '{product}' and added to {store.capitalize()} cart.*{link_part}"
            else:
                msg = f"Action confirmed and completed."
            await self.messaging_channel.send_text(user_id, msg)
            return {"status": "approved", "message": msg, "tool_result": tool_res.data}
        else:
            msg = "Action cancelled as requested."
            await self.messaging_channel.send_text(user_id, msg)
            return {"status": "rejected", "message": msg}


cascade_orchestrator = CascadeOrchestrator()
