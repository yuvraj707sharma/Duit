"""Repository layer managing database persistence for FastAgent."""
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import PendingApproval, AuditLog, IdempotencyRecord, LearningCorrection, utc_now


class DatabaseRepository:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        # In-memory fast layer backed by database schema
        self.approvals_store: Dict[str, Dict[str, Any]] = {}
        self.audit_log_store: List[Dict[str, Any]] = []
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        self.webhook_dedupe_store: Dict[str, Dict[str, Any]] = {}
        self.tokens_store: Dict[str, Dict[str, Any]] = {}
        self.users_store: Dict[str, Dict[str, Any]] = {
            "919876543210": {
                "id": "f902526d-66d8-49c3-b2b5-5fe95c870be6",
                "phone_number": "919876543210",
                "email": "primary@fastagent.dev",
                "display_name": "Primary Dev User",
                "created_at": time.time(),
                "services_connected": {"google": True, "desktop": True}
            }
        }
        self.skills_store: Dict[str, Dict[str, Any]] = {
            "skill_expense": {
                "id": "skill_expense",
                "user_id": "GLOBAL",
                "name": "Receipt & Expense Tracker",
                "slug": "expense_tracker",
                "description": "Extracts items, amounts, tax, vendors, and categories from receipts or expense texts.",
                "system_prompt": "You are an expert Expense Tracker. Analyze the user's receipt or expense notes. Extract: 1. Vendor/Store 2. Items & Amounts 3. Total Amount & Currency 4. Date 5. Category (Food, Travel, Bills, Work, Personal). Output a clean, markdown expense summary table.",
                "trigger_keywords": "expense, bill, receipt, kharcha, spend, paid, invoice",
                "webhook_url": None,
                "is_active": True,
                "created_at": time.time()
            },
            "skill_action_items": {
                "id": "skill_action_items",
                "user_id": "GLOBAL",
                "name": "Meeting Action Item Extractor",
                "slug": "action_items",
                "description": "Extracts tasks, assignees, deadlines, and next steps from meeting transcripts or discussion notes.",
                "system_prompt": "You are an Executive Chief of Staff. Extract all actionable decisions and tasks from the meeting notes or text. Output a markdown table with: Task, Assignee/Owner, Deadline, Priority (Urgent/Normal), and Recommended Next Steps.",
                "trigger_keywords": "action items, meeting minutes, mom, meeting notes, action tasks, discussion notes",
                "webhook_url": None,
                "is_active": True,
                "created_at": time.time()
            },
            "skill_copywriter": {
                "id": "skill_copywriter",
                "user_id": "GLOBAL",
                "name": "Sales Outreach Copywriter",
                "slug": "sales_copywriter",
                "description": "Crafts high-converting B2B outreach messages, cold emails, and pitch proposals.",
                "system_prompt": "You are a World-Class B2B Copywriter. Craft high-converting cold emails or messages using PAS (Problem-Agitate-Solution). Include: 1. Compelling subject lines 2. Personalized hook 3. Value proposition 4. Clear low-friction CTA. Keep under 120 words.",
                "trigger_keywords": "cold email, pitch, outreach, copy, sales message, proposal",
                "webhook_url": None,
                "is_active": True,
                "created_at": time.time()
            },
            "skill_code_debugger": {
                "id": "skill_code_debugger",
                "user_id": "GLOBAL",
                "name": "Code Reviewer & Debugger",
                "slug": "code_debugger",
                "description": "Analyzes code snippets, explains errors/stack traces, and provides tested clean fixes.",
                "system_prompt": "You are a Principal Software Engineer. Diagnose the code or stack trace, explain the root cause concisely, and provide the minimal, tested fix code snippet with clean documentation.",
                "trigger_keywords": "code, error, bug, trace, python, debug, fix, traceback",
                "webhook_url": None,
                "is_active": True,
                "created_at": time.time()
            }
        }


    async def create_pending_approval(
        self,
        user_id: str,
        request_id: str,
        query_text: str,
        intent: str,
        risk: str,
        confidence: float,
        arguments: Dict[str, Any],
        expires_in_seconds: int = 300
    ) -> Dict[str, Any]:
        now = time.time()
        expires_at = now + expires_in_seconds
        
        # Enforce Fix 2: Single pending approval per user (supersede prior pending)
        for aid, rec in self.approvals_store.items():
            if rec["user_id"] == user_id and rec["status"] == "pending":
                rec["status"] = "superseded"
                rec["resolved_at"] = now

        approval_id = str(uuid.uuid4())
        record = {
            "id": approval_id,
            "user_id": user_id,
            "request_id": request_id,
            "query_text": query_text,
            "intent": intent,
            "risk": risk,
            "confidence": confidence,
            "arguments": arguments,
            "status": "pending",
            "created_at": now,
            "expires_at": expires_at,
            "resolved_at": None
        }
        self.approvals_store[approval_id] = record
        return record

    async def get_user_pending_approvals(self, user_id: str) -> List[Dict[str, Any]]:
        now = time.time()
        results = []
        for rec in self.approvals_store.values():
            if rec["user_id"] == user_id:
                # Check 5-minute expiry
                if rec["status"] == "pending" and now > rec["expires_at"]:
                    rec["status"] = "expired"
                results.append(rec)
        return results

    async def get_approval_by_id(self, approval_id: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        rec = self.approvals_store.get(approval_id)
        if rec and rec["status"] == "pending" and now > rec["expires_at"]:
            rec["status"] = "expired"
        return rec

    async def resolve_approval(
        self,
        approval_id: str,
        decision: str,  # approve, edit, reject
        caller_user_id: str,
        edited_payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        rec = await self.get_approval_by_id(approval_id)
        if not rec:
            return {"error": "Approval request not found"}

        # Caller validation
        if rec["user_id"] != caller_user_id:
            return {"error": "Unauthorized: caller does not own this approval"}

        if rec["status"] == "expired":
            return {"error": "Approval request has expired (5-minute limit)"}

        if rec["status"] != "pending":
            return {"error": f"Approval is not pending (current status: {rec['status']})"}

        now = time.time()
        rec["status"] = decision
        rec["resolved_at"] = now
        if decision == "edit" and edited_payload:
            rec["arguments"].update(edited_payload)

        return {"status": decision, "record": rec}

    async def cancel_user_pending_approvals(self, user_id: str) -> int:
        """Emergency halt: cancels all pending approvals for a user and returns count."""
        now = time.time()
        count = 0
        for rec in self.approvals_store.values():
            if rec["user_id"] == user_id and rec["status"] == "pending":
                rec["status"] = "cancelled"
                rec["resolved_at"] = now
                count += 1
        return count

    async def insert_audit_log(self, record: Dict[str, Any]):
        """Insert-only audit log persisted in memory and PostgreSQL."""
        record["created_at"] = record.get("created_at") or time.time()
        record["id"] = record.get("id") or str(uuid.uuid4())
        self.audit_log_store.append(record)

        if self.session_factory:
            try:
                from backend.app.db.models import AuditLog as AuditLogModel
                async with self.session_factory() as session:
                    async with session.begin():
                        audit_entry = AuditLogModel(
                            user_id=record.get("user_id"),
                            request_id=record.get("request_id"),
                            raw_intent=record.get("raw_intent", "other"),
                            risk_level=record.get("risk_level", "low"),
                            confidence=float(record.get("confidence", 0.0)),
                            tools_called=record.get("tools_called", []),
                            was_confirmed=bool(record.get("was_confirmed", False)),
                            status=record.get("status", "executed"),
                            stage_latencies_ms=record.get("stage_latencies_ms", {})
                        )
                        session.add(audit_entry)
            except Exception:
                pass

    async def get_audit_logs(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        logs = self.audit_log_store
        if user_id:
            logs = [l for l in logs if l.get("user_id") == user_id]
        return logs[-limit:][::-1]

    async def get_idempotent_response(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        key = f"{user_id}:{idempotency_key}"
        res = self.idempotency_store.get(key)
        if res:
            return res
        if self.session_factory:
            try:
                from backend.app.db.models import IdempotencyRecord
                async with self.session_factory() as session:
                    stmt = select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == idempotency_key)
                    db_res = await session.execute(stmt)
                    rec = db_res.scalar_one_or_none()
                    if rec:
                        self.idempotency_store[key] = rec.response_payload
                        return rec.response_payload
            except Exception:
                pass
        return None

    async def save_idempotent_response(self, user_id: str, idempotency_key: str, response: Dict[str, Any]):
        key = f"{user_id}:{idempotency_key}"
        self.idempotency_store[key] = response

        if self.session_factory:
            try:
                from backend.app.db.models import IdempotencyRecord
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == idempotency_key)
                        db_res = await session.execute(stmt)
                        existing = db_res.scalar_one_or_none()
                        if existing:
                            existing.response_payload = response
                        else:
                            session.add(IdempotencyRecord(
                                user_id=user_id,
                                idempotency_key=idempotency_key,
                                action=response.get("intent", "other"),
                                response_payload=response
                            ))
            except Exception:
                pass

    async def get_webhook_dedupe(self, message_id: str) -> Optional[Dict[str, Any]]:
        res = self.webhook_dedupe_store.get(message_id)
        if res:
            return res
        if self.session_factory:
            try:
                from backend.app.db.models import IdempotencyRecord
                async with self.session_factory() as session:
                    stmt = select(IdempotencyRecord).where(IdempotencyRecord.message_id == message_id)
                    db_res = await session.execute(stmt)
                    rec = db_res.scalar_one_or_none()
                    if rec:
                        self.webhook_dedupe_store[message_id] = rec.response_payload
                        return rec.response_payload
            except Exception:
                pass
        return None

    async def save_webhook_dedupe(self, message_id: str, response: Dict[str, Any]):
        self.webhook_dedupe_store[message_id] = response

        if self.session_factory:
            try:
                from backend.app.db.models import IdempotencyRecord
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(IdempotencyRecord).where(IdempotencyRecord.message_id == message_id)
                        db_res = await session.execute(stmt)
                        existing = db_res.scalar_one_or_none()
                        if existing:
                            existing.response_payload = response
                        else:
                            session.add(IdempotencyRecord(
                                user_id=response.get("user_id", "system"),
                                idempotency_key=f"dedupe_{message_id}",
                                message_id=message_id,
                                action=response.get("intent", "webhook_inbound"),
                                response_payload=response
                            ))
            except Exception:
                pass

    async def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        cleaned = phone.strip().lstrip("+")
        return self.users_store.get(cleaned)

    async def register_user(
        self,
        phone: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None
    ) -> Dict[str, Any]:
        cleaned = phone.strip().lstrip("+")
        from backend.app.channels.base import get_user_uuid_from_channel_id
        user_uuid = get_user_uuid_from_channel_id(cleaned)
        user = {
            "id": user_uuid,
            "phone_number": cleaned,
            "email": email,
            "display_name": display_name or f"User {cleaned[-4:]}",
            "created_at": time.time(),
            "services_connected": {
                "google": False,
                "desktop": False
            }
        }
        self.users_store[cleaned] = user
        return user

    async def is_user_registered(self, phone: str) -> bool:
        cleaned = phone.strip().lstrip("+")
        return cleaned in self.users_store

    async def get_user(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieves user by phone number or UUID."""
        cleaned = identifier.strip().lstrip("+")
        if cleaned in self.users_store:
            return self.users_store[cleaned]
        for user in self.users_store.values():
            if user.get("id") == identifier or user.get("phone_number") == cleaned:
                return user
        return None

    async def save_user_oauth_tokens(
        self,
        user_id: str,
        provider: str,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str] = None,
        expires_at: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Saves encrypted OAuth tokens in memory and PostgreSQL OAuthToken table."""
        record = {
            "user_id": user_id,
            "provider": provider,
            "encrypted_access_token": encrypted_access_token,
            "encrypted_refresh_token": encrypted_refresh_token,
            "expires_at": expires_at,
            "updated_at": time.time()
        }
        self.tokens_store[user_id] = record

        # Link to user and mark Google connected
        user = await self.get_user(user_id)
        if user:
            user_uuid = user.get("id")
            phone = user.get("phone_number")
            if user_uuid:
                self.tokens_store[user_uuid] = record
            if phone:
                self.tokens_store[phone] = record
            user.setdefault("services_connected", {})["google"] = True

        # If PostgreSQL session factory is configured, persist to database
        if self.session_factory:
            try:
                from backend.app.db.models import OAuthToken, User as UserModel
                async with self.session_factory() as session:
                    async with session.begin():
                        # Find or create user record
                        stmt = select(UserModel).where(UserModel.id == user_id)
                        res = await session.execute(stmt)
                        db_user = res.scalar_one_or_none()
                        if not db_user and user:
                            db_user = UserModel(
                                id=user.get("id", user_id),
                                phone_number=user.get("phone_number"),
                                email=user.get("email")
                            )
                            session.add(db_user)

                        # Upsert token
                        token_stmt = select(OAuthToken).where(
                            and_(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
                        )
                        t_res = await session.execute(token_stmt)
                        token_obj = t_res.scalar_one_or_none()
                        if token_obj:
                            token_obj.encrypted_access_token = encrypted_access_token
                            if encrypted_refresh_token:
                                token_obj.encrypted_refresh_token = encrypted_refresh_token
                            token_obj.expires_at = expires_at
                        else:
                            token_obj = OAuthToken(
                                user_id=user_id,
                                provider=provider,
                                encrypted_access_token=encrypted_access_token,
                                encrypted_refresh_token=encrypted_refresh_token,
                                expires_at=expires_at
                            )
                            session.add(token_obj)
            except Exception:
                pass  # Fallback to in-memory store if DB is offline

        return record

    async def get_user_oauth_tokens(
        self,
        user_id: str,
        provider: str = "google"
    ) -> Optional[Dict[str, Any]]:
        """Retrieves user's encrypted OAuth tokens."""
        # 1. Fast in-memory lookup
        if user_id in self.tokens_store:
            rec = self.tokens_store[user_id]
            if rec.get("provider") == provider:
                return rec

        user = await self.get_user(user_id)
        if user:
            u_id = user.get("id")
            phone = user.get("phone_number")
            if u_id and u_id in self.tokens_store:
                return self.tokens_store[u_id]
            if phone and phone in self.tokens_store:
                return self.tokens_store[phone]

        # 2. Database lookup if session factory available
        if self.session_factory:
            try:
                from backend.app.db.models import OAuthToken
                async with self.session_factory() as session:
                    token_stmt = select(OAuthToken).where(
                        and_(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
                    )
                    t_res = await session.execute(token_stmt)
                    token_obj = t_res.scalar_one_or_none()
                    if token_obj:
                        rec = {
                            "user_id": token_obj.user_id,
                            "provider": token_obj.provider,
                            "encrypted_access_token": token_obj.encrypted_access_token,
                            "encrypted_refresh_token": token_obj.encrypted_refresh_token,
                            "expires_at": token_obj.expires_at
                        }
                        self.tokens_store[user_id] = rec
                        return rec
            except Exception:
                pass

        # 3. Direct lookup in MySQL gateway database (Duit_wa.google_tokens)
        if provider == "google":
            try:
                import pymysql
                clean_phone = user_id.replace("+", "").strip()
                conn = pymysql.connect(
                    host="localhost",
                    user="root",
                    password="Mysqlserver469",
                    database="Duit_wa",
                    cursorclass=pymysql.cursors.DictCursor
                )
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT phone, email, access_token, refresh_token, expiry_date FROM google_tokens WHERE phone = %s OR phone = %s LIMIT 1",
                        (clean_phone, f"+{clean_phone}")
                    )
                    row = cur.fetchone()
                    if row and (row.get("access_token") or row.get("refresh_token")):
                        rec = {
                            "user_id": user_id,
                            "provider": "google",
                            "access_token": row.get("access_token"),
                            "refresh_token": row.get("refresh_token"),
                            "expires_at": row.get("expiry_date"),
                            "email": row.get("email")
                        }
                        self.tokens_store[user_id] = rec
                        conn.close()
                        return rec
                conn.close()
            except Exception:
                pass

        return None

    async def list_skills(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists skills accessible to the user (GLOBAL skills + user-specific skills)."""
        res = []
        for s in self.skills_store.values():
            if not s.get("is_active", True):
                continue
            if s.get("user_id") == "GLOBAL" or s.get("user_id") == user_id:
                res.append(s)
        return res

    async def add_skill(
        self,
        name: str,
        system_prompt: str,
        user_id: str = "GLOBAL",
        description: str = "",
        trigger_keywords: str = "",
        webhook_url: Optional[str] = None,
        slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates or registers a new skill."""
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        computed_slug = slug or name.lower().replace(" ", "_")[:32]
        skill = {
            "id": skill_id,
            "user_id": user_id,
            "name": name,
            "slug": computed_slug,
            "description": description or f"Custom agent skill for {name}",
            "system_prompt": system_prompt,
            "trigger_keywords": trigger_keywords,
            "webhook_url": webhook_url,
            "is_active": True,
            "created_at": time.time()
        }
        self.skills_store[skill_id] = skill
        return skill

    async def delete_skill(self, skill_id: str) -> bool:
        """Deactivates or removes a skill."""
        if skill_id in self.skills_store:
            del self.skills_store[skill_id]
            return True
        return False

    async def find_matching_skill(self, user_id: Optional[str], text: str) -> Optional[Dict[str, Any]]:
        """Finds any active skill whose name, slug, or trigger keywords match the message text."""
        if not text:
            return None
        text_lower = text.lower()
        skills = await self.list_skills(user_id)

        for skill in skills:
            # 1. Exact or partial match on name or slug
            name_lower = skill.get("name", "").lower()
            slug_lower = skill.get("slug", "").lower()
            if name_lower and name_lower in text_lower:
                return skill
            if slug_lower and slug_lower in text_lower:
                return skill

            # 2. Check trigger keywords (comma-separated)
            keywords = [k.strip() for k in skill.get("trigger_keywords", "").lower().split(",") if k.strip()]
            for kw in keywords:
                # Match keyword as word boundary or substring
                if kw in text_lower:
                    return skill

        return None


from backend.app.db.database import AsyncSessionLocal

repository = DatabaseRepository(session_factory=AsyncSessionLocal)
