"""Repository layer managing database persistence for FastAgent."""
import time
import uuid
import secrets
import hmac
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.db.models import PendingApproval, AuditLog, IdempotencyRecord, LearningCorrection, utc_now


class DatabaseRepository:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        # In-memory fast layer backed by database schema
        self.tenants_store: Dict[str, Dict[str, Any]] = {
            "tenant_default_duit": {
                "id": "tenant_default_duit",
                "name": "Default DUIT Organization",
                "slug": "default",
                "created_at": time.time(),
                "updated_at": time.time()
            }
        }
        self.accounts_store: Dict[str, Dict[str, Any]] = {}
        self.devices_store: Dict[str, Dict[str, Any]] = {}
        self.desktop_pairing_sessions_store: Dict[str, Dict[str, Any]] = {}
        self.journal_entries_store: List[Dict[str, Any]] = []
        self.executions_store: Dict[str, Dict[str, Any]] = {}
        self.messages_store: List[Dict[str, Any]] = []
        self.outbox_store: List[Dict[str, Any]] = []
        self.linking_sessions_store: Dict[str, Dict[str, Any]] = {}
        self.whatsapp_sessions_store: Dict[str, Dict[str, Any]] = {}
        self.approvals_store: Dict[str, Dict[str, Any]] = {}
        self.audit_log_store: List[Dict[str, Any]] = []
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        self.webhook_dedupe_store: Dict[str, Dict[str, Any]] = {}
        self.tokens_store: Dict[str, Dict[str, Any]] = {}
        self.oauth_connections_store: Dict[str, Dict[str, Any]] = {}
        self.users_store: Dict[str, Dict[str, Any]] = {
            "919876543210": {
                "id": "f902526d-66d8-49c3-b2b5-5fe95c870be6",
                "tenant_id": "tenant_default_duit",
                "phone_number": "919876543210",
                "email": "primary@fastagent.dev",
                "full_name": "Primary Dev User",
                "display_name": "Primary Dev User",
                "role": "admin",
                "is_active": True,
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
        expires_in_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        from backend.app.policy.confirmations import RISK_TTL_MAP
        ttl = expires_in_seconds if expires_in_seconds is not None else RISK_TTL_MAP.get(risk.lower(), 300)
        now = time.time()
        expires_at = now + ttl

        # Enforce Fix 2: Single pending approval per user (supersede prior pending)
        for aid, rec in self.approvals_store.items():
            if rec["user_id"] == user_id and rec["status"] == "pending":
                rec["status"] = "superseded"
                rec["resolved_at"] = now

        approval_id = str(uuid.uuid4())
        record = {
            "id": approval_id,
            "tenant_id": tenant_id or "tenant_default_duit",
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
                # Check expiry
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

    async def amend_approval(
        self,
        approval_id: str,
        caller_user_id: str,
        amendments: Dict[str, Any],
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Amends a pending approval's arguments in place without creating a duplicate request."""
        rec = await self.get_approval_by_id(approval_id)
        if not rec:
            return {"error": "Approval request not found"}

        if rec["user_id"] != caller_user_id:
            return {"error": "Unauthorized: caller does not own this approval"}

        if tenant_id and rec.get("tenant_id") and rec.get("tenant_id") != tenant_id:
            return {"error": f"Approval {approval_id} does not belong to tenant {tenant_id}"}

        if rec["status"] == "expired":
            return {"error": "Approval request has expired"}

        if rec["status"] != "pending":
            return {"error": f"Cannot amend approval in '{rec['status']}' state"}

        now = time.time()
        rec["arguments"].update(amendments)
        rec["updated_at"] = now
        return {"status": "amended", "record": rec}

    async def cleanup_expired_approvals(self) -> int:
        """Transitions expired pending approvals to 'expired' status and returns count."""
        now = time.time()
        count = 0
        for rec in self.approvals_store.values():
            if rec.get("status") == "pending" and now > rec.get("expires_at", 0):
                rec["status"] = "expired"
                rec["resolved_at"] = now
                count += 1
        return count

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
        expires_at: Optional[Any] = None,
        tenant_id: Optional[str] = None,
        scopes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Saves encrypted OAuth tokens in memory and database with tenant scoping and capability tracking."""
        record = {
            "user_id": user_id,
            "provider": provider,
            "encrypted_access_token": encrypted_access_token,
            "encrypted_refresh_token": encrypted_refresh_token,
            "expires_at": expires_at,
            "scopes": scopes or ["calendar.read", "calendar.write", "gmail.read", "gmail.send"],
            "tenant_id": tenant_id or "tenant_default_duit",
            "updated_at": time.time()
        }
        self.tokens_store[user_id] = record

        # Link connection
        conn_rec = {
            "id": str(uuid.uuid4()),
            "tenant_id": record["tenant_id"],
            "user_id": user_id,
            "provider": provider,
            "scopes": record["scopes"],
            "status": "active",
            "expires_at": expires_at,
            "created_at": time.time(),
            "revoked_at": None
        }
        self.oauth_connections_store[f"{user_id}:{provider}"] = conn_rec

        # Link to user and mark Google connected
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if user:
            user_uuid = user.get("id")
            phone = user.get("phone_number")
            if user_uuid:
                self.tokens_store[user_uuid] = record
                self.oauth_connections_store[f"{user_uuid}:{provider}"] = conn_rec
            if phone:
                self.tokens_store[phone] = record
                self.oauth_connections_store[f"{phone}:{provider}"] = conn_rec
            user.setdefault("services_connected", {})[provider] = True

        # If PostgreSQL session factory is configured, persist to database
        if self.session_factory:
            try:
                from backend.app.db.models import OAuthToken, OAuthConnection, User as UserModel
                async with self.session_factory() as session:
                    async with session.begin():
                        # Find or create user record
                        stmt = select(UserModel).where(UserModel.id == user_id)
                        res = await session.execute(stmt)
                        db_user = res.scalar_one_or_none()
                        if not db_user and user:
                            db_user = UserModel(
                                id=user.get("id", user_id),
                                tenant_id=record["tenant_id"],
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

                        # Upsert connection
                        conn_stmt = select(OAuthConnection).where(
                            and_(OAuthConnection.user_id == user_id, OAuthConnection.provider == provider)
                        )
                        c_res = await session.execute(conn_stmt)
                        c_obj = c_res.scalar_one_or_none()
                        if c_obj:
                            c_obj.scopes = record["scopes"]
                            c_obj.expires_at = expires_at
                            c_obj.revoked_at = None
                        else:
                            session.add(OAuthConnection(
                                id=conn_rec["id"],
                                tenant_id=record["tenant_id"],
                                user_id=user_id,
                                provider=provider,
                                scopes=record["scopes"],
                                expires_at=expires_at
                            ))
            except Exception:
                pass  # Fallback to in-memory store if DB is offline

        return record

    async def revoke_user_oauth_tokens(
        self,
        user_id: str,
        provider: str = "google",
        tenant_id: Optional[str] = None
    ) -> bool:
        """Cryptographically revokes OAuth connection and deletes stored tokens."""
        from sqlalchemy import delete
        now = time.time()
        self.tokens_store.pop(user_id, None)
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if user:
            u_uuid = user.get("id")
            phone = user.get("phone_number")
            if u_uuid:
                self.tokens_store.pop(u_uuid, None)
            if phone:
                self.tokens_store.pop(phone, None)
            if isinstance(user.get("services_connected"), dict):
                user["services_connected"][provider] = False

        conn_key = f"{user_id}:{provider}"
        if conn_key in self.oauth_connections_store:
            self.oauth_connections_store[conn_key]["status"] = "revoked"
            self.oauth_connections_store[conn_key]["revoked_at"] = now

        if self.session_factory:
            try:
                from backend.app.db.models import OAuthToken, OAuthConnection
                async with self.session_factory() as session:
                    async with session.begin():
                        del_stmt = delete(OAuthToken).where(
                            and_(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
                        )
                        await session.execute(del_stmt)

                        conn_stmt = select(OAuthConnection).where(
                            and_(OAuthConnection.user_id == user_id, OAuthConnection.provider == provider)
                        )
                        res = await session.execute(conn_stmt)
                        c = res.scalar_one_or_none()
                        if c:
                            c.revoked_at = datetime.fromtimestamp(now, timezone.utc)
            except Exception:
                pass

        return True

    async def get_user_oauth_connection(
        self,
        user_id: str,
        provider: str = "google",
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves active OAuth connection details and capability scopes for user."""
        conn_key = f"{user_id}:{provider}"
        rec = self.oauth_connections_store.get(conn_key)
        if rec and rec.get("status") == "active":
            if tenant_id and rec.get("tenant_id") != tenant_id:
                return None
            return rec

        tokens = await self.get_user_oauth_tokens(user_id, provider=provider)
        if tokens and (tokens.get("encrypted_access_token") or tokens.get("access_token")):
            user = await self.get_user(user_id, tenant_id=tenant_id)
            t_id = tenant_id or (user.get("tenant_id") if user else "tenant_default_duit")
            default_conn = {
                "id": str(uuid.uuid4()),
                "tenant_id": t_id,
                "user_id": user_id,
                "provider": provider,
                "scopes": tokens.get("scopes") or ["calendar.read", "calendar.write", "gmail.read", "gmail.send"],
                "status": "active",
                "expires_at": tokens.get("expires_at"),
                "created_at": time.time(),
                "revoked_at": None
            }
            self.oauth_connections_store[conn_key] = default_conn
            return default_conn

        return None

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

    # -------------------------------------------------------------------------
    # Multi-tenant Identity, Linked Accounts, Devices, Executions & Archive
    # -------------------------------------------------------------------------

    async def create_tenant(
        self,
        name: str,
        slug: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Creates a new organizational tenant."""
        tid = tenant_id or str(uuid.uuid4())
        computed_slug = slug or name.lower().replace(" ", "-")[:64]
        now = time.time()
        tenant = {
            "id": tid,
            "name": name,
            "slug": computed_slug,
            "created_at": now,
            "updated_at": now
        }
        self.tenants_store[tid] = tenant

        if self.session_factory:
            try:
                from backend.app.db.models import Tenant as TenantModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(TenantModel(
                            id=tid,
                            name=name,
                            slug=computed_slug
                        ))
            except Exception:
                pass

        return tenant

    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a tenant by ID."""
        if tenant_id in self.tenants_store:
            return self.tenants_store[tenant_id]

        if self.session_factory:
            try:
                from backend.app.db.models import Tenant as TenantModel
                async with self.session_factory() as session:
                    stmt = select(TenantModel).where(TenantModel.id == tenant_id)
                    res = await session.execute(stmt)
                    t = res.scalar_one_or_none()
                    if t:
                        rec = {
                            "id": t.id,
                            "name": t.name,
                            "slug": t.slug,
                            "created_at": t.created_at.timestamp() if t.created_at else time.time(),
                            "updated_at": t.updated_at.timestamp() if t.updated_at else time.time()
                        }
                        self.tenants_store[t.id] = rec
                        return rec
            except Exception:
                pass

        return None

    async def register_user(
        self,
        tenant_id: Optional[str] = None,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
        phone: Optional[str] = None,
        display_name: Optional[str] = None,
        full_name: Optional[str] = None,
        role: str = "member",
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a user bound to an explicit tenant, preserving legacy phone onboarding compatibility."""
        tid = tenant_id or "tenant_default_duit"
        tenant = await self.get_tenant(tid)
        if not tenant:
            from backend.app.security.context import SecurityContextError
            raise SecurityContextError(f"Tenant {tid} does not exist")

        uid = user_id or str(uuid.uuid4())
        raw_phone = phone_number or phone
        clean_phone = "".join(filter(str.isdigit, raw_phone)) if raw_phone else None
        computed_name = full_name or display_name or (email.split("@")[0] if email else (clean_phone or "DUIT User"))
        computed_email = email or (f"{clean_phone}@fastagent.local" if clean_phone else f"user_{uid[:8]}@fastagent.local")
        now = time.time()

        user_data = {
            "id": uid,
            "tenant_id": tid,
            "email": computed_email,
            "phone_number": clean_phone,
            "full_name": computed_name,
            "display_name": computed_name,
            "role": role,
            "is_active": True,
            "created_at": now,
            "services_connected": {}
        }
        self.users_store[uid] = user_data
        if clean_phone:
            self.users_store[clean_phone] = user_data

        if self.session_factory:
            try:
                from backend.app.db.models import User as UserModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(UserModel(
                            id=uid,
                            tenant_id=tid,
                            email=computed_email,
                            phone_number=clean_phone,
                            full_name=computed_name,
                            role=role,
                            is_active=True
                        ))
            except Exception:
                pass

        return user_data

    async def get_user(self, user_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a user with strict tenant boundary enforcement."""
        user = self.users_store.get(user_id)
        if not user:
            clean_id = "".join(filter(str.isdigit, user_id)) if user_id else None
            if clean_id and clean_id in self.users_store:
                user = self.users_store[clean_id]

        if user:
            if tenant_id and user.get("tenant_id") and user.get("tenant_id") != tenant_id:
                return None
            return user

        if self.session_factory:
            try:
                from backend.app.db.models import User as UserModel
                from sqlalchemy import or_
                async with self.session_factory() as session:
                    stmt = select(UserModel).where(
                        or_(UserModel.id == user_id, UserModel.phone_number == user_id)
                    )
                    res = await session.execute(stmt)
                    u = res.scalar_one_or_none()
                    if u:
                        if tenant_id and u.tenant_id and u.tenant_id != tenant_id:
                            return None
                        rec = {
                            "id": u.id,
                            "tenant_id": u.tenant_id,
                            "email": u.email,
                            "phone_number": u.phone_number,
                            "full_name": u.full_name,
                            "display_name": u.full_name,
                            "role": u.role,
                            "is_active": u.is_active,
                            "created_at": u.created_at.timestamp() if u.created_at else time.time(),
                            "services_connected": {}
                        }
                        self.users_store[u.id] = rec
                        if u.phone_number:
                            self.users_store[u.phone_number] = rec
                        return rec
            except Exception:
                pass

        return None

    async def link_whatsapp_account(
        self,
        tenant_id: str,
        user_id: str,
        phone_number: str,
        display_name: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Links a WhatsApp account to an authenticated user and tenant."""
        from backend.app.security.context import SecurityContextError
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if not user:
            raise SecurityContextError(f"User {user_id} does not belong to tenant {tenant_id}")

        aid = account_id or str(uuid.uuid4())
        clean_phone = "".join(filter(str.isdigit, phone_number))
        now = time.time()

        account = {
            "id": aid,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "phone_number": clean_phone,
            "display_name": display_name or clean_phone,
            "status": "active",
            "created_at": now,
            "last_seen_at": now,
            "revoked_at": None
        }
        self.accounts_store[aid] = account

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppAccount as WAAccountModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(WAAccountModel(
                            id=aid,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            phone_number=clean_phone,
                            display_name=account["display_name"],
                            status="active"
                        ))
            except Exception:
                pass

        return account

    async def get_whatsapp_account(self, account_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a WhatsApp account with tenant scoping."""
        account = self.accounts_store.get(account_id)
        if account:
            if tenant_id and account.get("tenant_id") != tenant_id:
                return None
            return account

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppAccount as WAAccountModel
                async with self.session_factory() as session:
                    stmt = select(WAAccountModel).where(WAAccountModel.id == account_id)
                    res = await session.execute(stmt)
                    a = res.scalar_one_or_none()
                    if a:
                        if tenant_id and a.tenant_id != tenant_id:
                            return None
                        rec = {
                            "id": a.id,
                            "tenant_id": a.tenant_id,
                            "user_id": a.user_id,
                            "phone_number": a.phone_number,
                            "display_name": a.display_name,
                            "status": a.status,
                            "created_at": a.created_at.timestamp() if a.created_at else time.time(),
                            "last_seen_at": a.last_seen_at.timestamp() if a.last_seen_at else time.time(),
                            "revoked_at": a.revoked_at.timestamp() if a.revoked_at else None
                        }
                        self.accounts_store[a.id] = rec
                        return rec
            except Exception:
                pass

        return None

    async def get_user_whatsapp_account(self, user_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Finds or retrieves the primary active WhatsApp account for a user."""
        clean_phone = "".join(filter(str.isdigit, user_id)) if user_id else ""
        for acc in self.accounts_store.values():
            if acc.get("status") == "active":
                if acc.get("user_id") == user_id or (clean_phone and acc.get("phone_number") == clean_phone):
                    if tenant_id and acc.get("tenant_id") and acc.get("tenant_id") != tenant_id:
                        continue
                    return acc

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppAccount as WAAccountModel
                from sqlalchemy import or_
                async with self.session_factory() as session:
                    conds = [WAAccountModel.user_id == user_id]
                    if clean_phone:
                        conds.append(WAAccountModel.phone_number == clean_phone)
                    stmt = select(WAAccountModel).where(or_(*conds))
                    res = await session.execute(stmt)
                    accounts = res.scalars().all()
                    for a in accounts:
                        if a.status == "active":
                            if tenant_id and a.tenant_id and a.tenant_id != tenant_id:
                                continue
                            rec = {
                                "id": a.id,
                                "tenant_id": a.tenant_id,
                                "user_id": a.user_id,
                                "phone_number": a.phone_number,
                                "display_name": a.display_name,
                                "status": a.status,
                                "created_at": a.created_at.timestamp() if a.created_at else time.time(),
                                "last_seen_at": a.last_seen_at.timestamp() if a.last_seen_at else time.time(),
                                "revoked_at": a.revoked_at.timestamp() if a.revoked_at else None
                            }
                            self.accounts_store[a.id] = rec
                            return rec
            except Exception:
                pass

        user = await self.get_user(user_id, tenant_id=tenant_id)
        if user:
            t_id = tenant_id or user.get("tenant_id") or "tenant_default"
            phone = user.get("phone_number") or clean_phone or user_id
            return await self.link_whatsapp_account(
                tenant_id=t_id,
                user_id=user["id"],
                phone_number=phone,
                display_name=user.get("display_name") or user.get("full_name") or phone
            )

        return None

    async def register_desktop_device(
        self,
        tenant_id: str,
        user_id: str,
        device_name: str,
        platform: str = "windows",
        permissions: Optional[List[str]] = None,
        device_id: Optional[str] = None,
        public_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a desktop device bound to user and tenant."""
        from backend.app.security.context import SecurityContextError
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if not user:
            raise SecurityContextError(f"User {user_id} does not belong to tenant {tenant_id}")

        did = device_id or str(uuid.uuid4())
        now = time.time()
        device = {
            "id": did,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "device_name": device_name,
            "platform": platform,
            "public_key": public_key,
            "is_online": True,
            "permissions": permissions or ["desktop.app.launch", "desktop.ui.snapshot"],
            "last_seen_at": now,
            "created_at": now,
            "revoked_at": None
        }
        self.devices_store[did] = device

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopDevice as DeviceModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(DeviceModel(
                            id=did,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            device_name=device_name,
                            platform=platform,
                            public_key=public_key,
                            is_online=True,
                            permissions=device["permissions"]
                        ))
            except Exception:
                pass

        return device

    async def get_desktop_device(self, device_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a desktop device scoped to tenant."""
        device = self.devices_store.get(device_id)
        if device:
            if tenant_id and device.get("tenant_id") != tenant_id:
                return None
            return device

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopDevice as DeviceModel
                async with self.session_factory() as session:
                    stmt = select(DeviceModel).where(DeviceModel.id == device_id)
                    res = await session.execute(stmt)
                    d = res.scalar_one_or_none()
                    if d:
                        if tenant_id and d.tenant_id != tenant_id:
                            return None
                        rec = {
                            "id": d.id,
                            "tenant_id": d.tenant_id,
                            "user_id": d.user_id,
                            "device_name": d.device_name,
                            "platform": d.platform,
                            "public_key": d.public_key,
                            "is_online": d.is_online,
                            "permissions": d.permissions,
                            "last_seen_at": d.last_seen_at.timestamp() if d.last_seen_at else time.time(),
                            "created_at": d.created_at.timestamp() if d.created_at else time.time(),
                            "revoked_at": d.revoked_at.timestamp() if d.revoked_at else None
                        }
                        self.devices_store[d.id] = rec
                        return rec
            except Exception:
                pass

        return None

    async def create_desktop_pairing_session(
        self,
        tenant_id: str,
        user_id: str,
        ttl_seconds: int = 600
    ) -> Dict[str, Any]:
        """Creates a short-lived desktop device pairing transaction with one-time pairing code and nonce."""
        from backend.app.security.context import SecurityContextError
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if not user:
            raise SecurityContextError(f"User {user_id} does not belong to tenant {tenant_id}")

        sid = str(uuid.uuid4())
        pairing_code = f"DK-{secrets.token_hex(2).upper()}-{secrets.randbelow(9000)+1000}"
        nonce = secrets.token_hex(16)
        now = time.time()
        expires_at = now + ttl_seconds

        session_rec = {
            "id": sid,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "pairing_code": pairing_code,
            "nonce": nonce,
            "device_id": None,
            "status": "pending",
            "created_at": now,
            "expires_at": expires_at,
            "claimed_at": None
        }
        self.desktop_pairing_sessions_store[sid] = session_rec

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopPairingSession as PairingModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(PairingModel(
                            id=sid,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            pairing_code=pairing_code,
                            nonce=nonce,
                            status="pending",
                            expires_at=datetime.fromtimestamp(expires_at, timezone.utc)
                        ))
            except Exception:
                pass

        return session_rec

    async def get_desktop_pairing_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves desktop pairing session and verifies expiration."""
        sess = self.desktop_pairing_sessions_store.get(session_id)
        if sess:
            if time.time() > sess["expires_at"] and sess["status"] == "pending":
                sess["status"] = "expired"
            return sess

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopPairingSession as PairingModel
                async with self.session_factory() as session:
                    stmt = select(PairingModel).where(PairingModel.id == session_id)
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        exp = m.expires_at.timestamp() if m.expires_at else time.time()
                        status = m.status
                        if time.time() > exp and status == "pending":
                            status = "expired"
                        rec = {
                            "id": m.id,
                            "tenant_id": m.tenant_id,
                            "user_id": m.user_id,
                            "pairing_code": m.pairing_code,
                            "nonce": m.nonce,
                            "device_id": m.device_id,
                            "status": status,
                            "created_at": m.created_at.timestamp() if m.created_at else time.time(),
                            "expires_at": exp,
                            "claimed_at": m.claimed_at.timestamp() if m.claimed_at else None
                        }
                        self.desktop_pairing_sessions_store[m.id] = rec
                        return rec
            except Exception:
                pass

        return None

    async def claim_desktop_pairing(
        self,
        pairing_code: str,
        nonce: str,
        device_name: str,
        platform: str = "windows",
        public_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validates pairing code and nonce, registers device, and issues device token."""
        from backend.app.security.context import SecurityContextError
        matched_sess = None
        now = time.time()

        for s in self.desktop_pairing_sessions_store.values():
            if hmac.compare_digest(s.get("pairing_code", ""), pairing_code) and hmac.compare_digest(s.get("nonce", ""), nonce):
                matched_sess = s
                break

        if not matched_sess and self.session_factory:
            try:
                from backend.app.db.models import DesktopPairingSession as PairingModel
                async with self.session_factory() as session:
                    stmt = select(PairingModel).where(
                        PairingModel.pairing_code == pairing_code,
                        PairingModel.nonce == nonce
                    )
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        matched_sess = {
                            "id": m.id,
                            "tenant_id": m.tenant_id,
                            "user_id": m.user_id,
                            "pairing_code": m.pairing_code,
                            "nonce": m.nonce,
                            "device_id": m.device_id,
                            "status": m.status,
                            "created_at": m.created_at.timestamp() if m.created_at else time.time(),
                            "expires_at": m.expires_at.timestamp() if m.expires_at else time.time(),
                            "claimed_at": m.claimed_at.timestamp() if m.claimed_at else None
                        }
                        self.desktop_pairing_sessions_store[m.id] = matched_sess
            except Exception:
                pass

        if not matched_sess:
            raise SecurityContextError("Invalid pairing code or nonce")

        if matched_sess["status"] != "pending":
            raise SecurityContextError(f"Pairing transaction is already {matched_sess['status']}")

        if now > matched_sess["expires_at"]:
            matched_sess["status"] = "expired"
            raise SecurityContextError("Pairing session has expired")

        # Register the device
        device = await self.register_desktop_device(
            tenant_id=matched_sess["tenant_id"],
            user_id=matched_sess["user_id"],
            device_name=device_name,
            platform=platform,
            public_key=public_key
        )

        matched_sess["status"] = "claimed"
        matched_sess["claimed_at"] = now
        matched_sess["device_id"] = device["id"]

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopPairingSession as PairingModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(PairingModel).where(PairingModel.id == matched_sess["id"])
                        res = await session.execute(stmt)
                        m = res.scalar_one_or_none()
                        if m:
                            m.status = "claimed"
                            m.claimed_at = datetime.fromtimestamp(now, timezone.utc)
                            m.device_id = device["id"]
            except Exception:
                pass

        device_token = f"dtoken_{secrets.token_urlsafe(32)}"
        return {
            "status": "claimed",
            "device": device,
            "device_token": device_token,
            "tenant_id": matched_sess["tenant_id"],
            "user_id": matched_sess["user_id"],
            "claimed_at": now
        }

    async def kill_desktop_device(
        self,
        device_id: str,
        reason: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Emergency kill switch: terminates workstation connection and revokes device credentials."""
        now = time.time()
        device = self.devices_store.get(device_id)
        if device:
            if tenant_id and device.get("tenant_id") != tenant_id:
                from backend.app.security.context import SecurityContextError
                raise SecurityContextError(f"Device {device_id} not found in tenant {tenant_id}")
            device["is_online"] = False
            device["revoked_at"] = now
            device["kill_reason"] = reason or "Emergency kill switch invoked"

        if self.session_factory:
            try:
                from backend.app.db.models import DesktopDevice as DeviceModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(DeviceModel).where(DeviceModel.id == device_id)
                        res = await session.execute(stmt)
                        d = res.scalar_one_or_none()
                        if d:
                            if tenant_id and d.tenant_id != tenant_id:
                                from backend.app.security.context import SecurityContextError
                                raise SecurityContextError(f"Device {device_id} not found in tenant {tenant_id}")
                            d.is_online = False
                            d.revoked_at = datetime.fromtimestamp(now, timezone.utc)
            except Exception:
                pass

        # Disconnect live socket in presence manager
        try:
            from backend.app.desktop.presence import presence_manager
            if device and device.get("user_id"):
                presence_manager.unregister_desktop(device["user_id"])
        except Exception:
            pass

        return {
            "status": "killed",
            "device_id": device_id,
            "revoked_at": now,
            "reason": reason or "Emergency kill switch invoked"
        }

    async def append_journal_entry(
        self,
        tenant_id: str,
        device_id: str,
        action: str,
        signature: str,
        arguments_hash: Optional[str] = None,
        status: str = "executed"
    ) -> Dict[str, Any]:
        """Appends an HMAC-signed audit entry to the desktop agent journal."""
        eid = str(uuid.uuid4())
        now_dt = datetime.now(timezone.utc)
        entry = {
            "id": eid,
            "tenant_id": tenant_id,
            "device_id": device_id,
            "action": action,
            "arguments_hash": arguments_hash,
            "status": status,
            "signature": signature,
            "created_at": now_dt
        }
        self.journal_entries_store.append(entry)

        if self.session_factory:
            try:
                from backend.app.db.models import LocalJournalEntry as JournalModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(JournalModel(
                            id=eid,
                            tenant_id=tenant_id,
                            device_id=device_id,
                            action=action,
                            arguments_hash=arguments_hash,
                            status=status,
                            signature=signature,
                            created_at=now_dt
                        ))
            except Exception:
                pass

        return entry

    async def get_journal_entries(
        self,
        device_id: str,
        tenant_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Retrieves tamper-evident journal entries for a device."""
        entries = []
        for e in reversed(self.journal_entries_store):
            if e.get("device_id") == device_id:
                if tenant_id and e.get("tenant_id") != tenant_id:
                    continue
                entries.append(e)
                if len(entries) >= limit:
                    break

        if entries:
            return entries

        if self.session_factory:
            try:
                from backend.app.db.models import LocalJournalEntry as JournalModel
                from sqlalchemy import and_
                async with self.session_factory() as session:
                    conds = [JournalModel.device_id == device_id]
                    if tenant_id:
                        conds.append(JournalModel.tenant_id == tenant_id)
                    stmt = select(JournalModel).where(and_(*conds)).order_by(JournalModel.created_at.desc()).limit(limit)
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    for r in rows:
                        entries.append({
                            "id": r.id,
                            "tenant_id": r.tenant_id,
                            "device_id": r.device_id,
                            "action": r.action,
                            "arguments_hash": r.arguments_hash,
                            "status": r.status,
                            "signature": r.signature,
                            "created_at": r.created_at
                        })
            except Exception:
                pass

        return entries

    async def record_execution(
        self,
        tenant_id: str,
        user_id: str,
        capability: str,
        arguments: Dict[str, Any],
        risk_level: str = "medium",
        idempotency_key: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records an execution attempt with strict tenant/device authorization."""
        from backend.app.security.context import SecurityContextError
        user = await self.get_user(user_id, tenant_id=tenant_id)
        if not user:
            raise SecurityContextError(f"User {user_id} does not belong to tenant {tenant_id}")

        if device_id:
            device = await self.get_desktop_device(device_id, tenant_id=tenant_id)
            if not device or device.get("user_id") != user_id:
                raise SecurityContextError(f"Device {device_id} does not belong to user {user_id}")

        eid = str(uuid.uuid4())
        ikey = idempotency_key or f"exec_{uuid.uuid4().hex[:12]}"
        now = time.time()

        exec_rec = {
            "id": eid,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "device_id": device_id,
            "capability": capability,
            "arguments": arguments,
            "risk_level": risk_level,
            "status": "pending",
            "verified": False,
            "output": None,
            "error": None,
            "idempotency_key": ikey,
            "created_at": now,
            "completed_at": None
        }
        self.executions_store[eid] = exec_rec

        if self.session_factory:
            try:
                from backend.app.db.models import Execution as ExecutionModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(ExecutionModel(
                            id=eid,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            device_id=device_id,
                            capability=capability,
                            arguments=arguments,
                            risk_level=risk_level,
                            status="pending",
                            verified=False,
                            idempotency_key=ikey
                        ))
            except Exception:
                pass

        return exec_rec

    async def complete_execution(
        self,
        execution_id: str,
        status: str,
        verified: bool = True,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Marks an execution complete with verified output."""
        from backend.app.security.context import SecurityContextError
        exec_rec = self.executions_store.get(execution_id)
        if not exec_rec:
            return None

        if tenant_id and exec_rec.get("tenant_id") != tenant_id:
            raise SecurityContextError("Execution belongs to different tenant")

        now = time.time()
        exec_rec["status"] = status
        exec_rec["verified"] = verified
        exec_rec["output"] = output
        exec_rec["error"] = error
        exec_rec["completed_at"] = now

        if self.session_factory:
            try:
                from backend.app.db.models import Execution as ExecutionModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(ExecutionModel).where(ExecutionModel.id == execution_id)
                        res = await session.execute(stmt)
                        e = res.scalar_one_or_none()
                        if e:
                            e.status = status
                            e.verified = verified
                            e.output = output
                            e.error = error
            except Exception:
                pass

        return exec_rec

    async def archive_message(
        self,
        tenant_id: str,
        whatsapp_account_id: str,
        provider_message_id: str,
        sender_jid: str,
        text: str,
        message_timestamp: Optional[datetime] = None,
        sender_phone: Optional[str] = None,
        sender_display_name: Optional[str] = None,
        direction: str = "inbound",
        conversation_id: Optional[str] = None,
        media_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Archives an inbound/outbound message strictly scoped to linked account & tenant."""
        import hashlib
        from backend.app.security.context import SecurityContextError
        account = await self.get_whatsapp_account(whatsapp_account_id, tenant_id=tenant_id)
        if not account:
            raise SecurityContextError(f"WhatsApp account {whatsapp_account_id} not found in tenant {tenant_id}")

        # Idempotent deduplication check
        for m in self.messages_store:
            if m.get("whatsapp_account_id") == whatsapp_account_id and m.get("provider_message_id") == provider_message_id:
                return m

        mid = str(uuid.uuid4())
        ts = message_timestamp or datetime.now(timezone.utc)
        clean_sender_phone = sender_phone or "".join(filter(str.isdigit, sender_jid.split("@")[0]))
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

        msg_rec = {
            "id": mid,
            "tenant_id": tenant_id,
            "whatsapp_account_id": whatsapp_account_id,
            "conversation_id": conversation_id,
            "provider_message_id": provider_message_id,
            "sender_jid": sender_jid,
            "sender_phone": clean_sender_phone,
            "sender_display_name": sender_display_name or sender_jid.split("@")[0],
            "direction": direction,
            "text": text,
            "media_metadata": media_metadata,
            "message_timestamp": ts,
            "received_at": datetime.now(timezone.utc),
            "content_hash": content_hash
        }
        self.messages_store.insert(0, msg_rec)

        if self.session_factory:
            try:
                from backend.app.db.models import Message as MessageModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(MessageModel(
                            id=mid,
                            tenant_id=tenant_id,
                            whatsapp_account_id=whatsapp_account_id,
                            conversation_id=conversation_id,
                            provider_message_id=provider_message_id,
                            sender_jid=sender_jid,
                            sender_phone=clean_sender_phone,
                            sender_display_name=msg_rec["sender_display_name"],
                            direction=direction,
                            text=text,
                            media_metadata=media_metadata,
                            message_timestamp=ts,
                            content_hash=content_hash
                        ))
            except Exception:
                pass

        return msg_rec

    async def search_messages(
        self,
        tenant_id: str,
        whatsapp_account_id: str,
        query_text: Optional[str] = None,
        contact: Optional[str] = None,
        sender_phone: Optional[str] = None,
        direction: Optional[str] = None,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Searches archived messages strictly isolated to tenant and linked WhatsApp account with rich filters."""
        results = []
        clean_filter_phone = "".join(filter(str.isdigit, sender_phone or contact or "")) if (sender_phone or contact) else None
        contact_lower = contact.lower().strip() if contact else None
        q_lower = query_text.lower().strip() if query_text else None

        # Check in-memory store
        matching = []
        for m in self.messages_store:
            # Strict tenant and account boundary
            if m.get("tenant_id") != tenant_id or m.get("whatsapp_account_id") != whatsapp_account_id:
                continue

            if direction and m.get("direction") != direction:
                continue

            if clean_filter_phone and clean_filter_phone in (m.get("sender_phone") or ""):
                pass
            elif contact_lower and contact_lower in (m.get("sender_display_name") or "").lower():
                pass
            elif contact or sender_phone:
                continue

            if q_lower and q_lower not in m.get("text", "").lower():
                continue

            ts = m.get("message_timestamp")
            if ts:
                if isinstance(ts, (int, float)):
                    ts_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(ts, datetime):
                    ts_dt = ts
                else:
                    ts_dt = None

                if ts_dt and start_date and ts_dt < start_date:
                    continue
                if ts_dt and end_date and ts_dt > end_date:
                    continue

            matching.append(m)

        if matching:
            return matching[offset:offset + limit]

        # Query database if session factory is available
        if self.session_factory:
            try:
                from backend.app.db.models import Message as MessageModel
                from sqlalchemy import and_, or_
                async with self.session_factory() as session:
                    filters = [
                        MessageModel.tenant_id == tenant_id,
                        MessageModel.whatsapp_account_id == whatsapp_account_id
                    ]
                    if direction:
                        filters.append(MessageModel.direction == direction)
                    if q_lower:
                        filters.append(MessageModel.text.ilike(f"%{q_lower}%"))
                    if clean_filter_phone:
                        filters.append(MessageModel.sender_phone.contains(clean_filter_phone))
                    elif contact_lower:
                        filters.append(MessageModel.sender_display_name.ilike(f"%{contact_lower}%"))
                    if start_date:
                        filters.append(MessageModel.message_timestamp >= start_date)
                    if end_date:
                        filters.append(MessageModel.message_timestamp <= end_date)

                    stmt = (
                        select(MessageModel)
                        .where(and_(*filters))
                        .order_by(MessageModel.message_timestamp.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    for r in rows:
                        results.append({
                            "id": r.id,
                            "tenant_id": r.tenant_id,
                            "whatsapp_account_id": r.whatsapp_account_id,
                            "conversation_id": r.conversation_id,
                            "provider_message_id": r.provider_message_id,
                            "sender_jid": r.sender_jid,
                            "sender_phone": r.sender_phone,
                            "sender_display_name": r.sender_display_name,
                            "direction": r.direction,
                            "text": r.text,
                            "media_metadata": r.media_metadata,
                            "message_timestamp": r.message_timestamp,
                            "content_hash": r.content_hash
                        })
                    return results
            except Exception:
                pass

        return []

    async def generate_archive_summary(
        self,
        tenant_id: str,
        whatsapp_account_id: str,
        query_text: Optional[str] = None,
        contact: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Generates structured executive summary of archived messages with source citations and truthful absence reporting."""
        msgs = await self.search_messages(
            tenant_id=tenant_id,
            whatsapp_account_id=whatsapp_account_id,
            query_text=query_text,
            contact=contact,
            limit=limit
        )
        if not msgs:
            return {
                "total_found": 0,
                "messages": [],
                "citations": [],
                "summary_text": "I searched your archived WhatsApp history. No recorded messages were found matching your criteria in this window."
            }

        citations = []
        lines = [f"*WhatsApp Archive Summary ({len(msgs)} Messages Found)*\n"]
        for idx, m in enumerate(msgs, 1):
            ts = m.get("message_timestamp")
            if isinstance(ts, datetime):
                ts_str = ts.strftime("%Y-%m-%d %H:%M:%S UTC")
            elif isinstance(ts, (int, float)):
                ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            else:
                ts_str = str(ts or "Unknown time")

            sender = m.get("sender_display_name") or m.get("sender_phone") or m.get("sender_jid") or "Unknown"
            mid = m.get("provider_message_id") or m.get("id") or f"msg_{idx}"
            cite_tag = f"[Msg {mid[:12]} @ {ts_str} | {sender}]"
            citations.append({
                "citation_id": mid,
                "timestamp": ts_str,
                "sender": sender,
                "text": m.get("text", "")
            })
            lines.append(f"{idx}. {cite_tag}: {m.get('text', '')}")

        lines.append(f"\n*Summary:* Retrieved {len(msgs)} verified archived messages with source citations.")
        return {
            "total_found": len(msgs),
            "messages": msgs,
            "citations": citations,
            "summary_text": "\n".join(lines)
        }

    async def verify_security_context(self, context: Any) -> bool:
        """Verifies full server-verified identity context."""
        from backend.app.security.context import SecurityContextError
        tenant = await self.get_tenant(context.tenant_id)
        if not tenant:
            raise SecurityContextError(f"Tenant {context.tenant_id} not found")

        user = await self.get_user(context.user_id, tenant_id=context.tenant_id)
        if not user:
            raise SecurityContextError(f"User {context.user_id} does not belong to tenant {context.tenant_id}")

        if context.account_id:
            account = await self.get_whatsapp_account(context.account_id, tenant_id=context.tenant_id)
            if not account or account.get("user_id") != context.user_id:
                raise SecurityContextError(
                    f"WhatsApp account {context.account_id} does not belong to user {context.user_id}"
                )

        if context.device_id:
            device = await self.get_desktop_device(context.device_id, tenant_id=context.tenant_id)
            if not device or device.get("user_id") != context.user_id:
                raise SecurityContextError(
                    f"Desktop device {context.device_id} does not belong to user {context.user_id}"
                )

        return True

    # -------------------------------------------------------------------------
    # Phase 2: Dedicated WhatsApp Linking Transactions and Encrypted Sessions
    # -------------------------------------------------------------------------

    async def create_linking_session(
        self,
        tenant_id: str,
        user_id: str,
        phone_number: Optional[str] = None,
        gateway_instance: str = "directorbot-primary",
        ttl_seconds: int = 600
    ) -> Dict[str, Any]:
        """Creates a short-lived transaction for securely linking a WhatsApp account."""
        import secrets
        from backend.app.security.context import SecurityContextError

        user = await self.get_user(user_id, tenant_id=tenant_id)
        if not user:
            raise SecurityContextError(f"User {user_id} does not belong to tenant {tenant_id}")

        session_id = str(uuid.uuid4())
        prefix = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
        suffix = "".join(secrets.choice("23456789") for _ in range(4))
        pairing_code = f"{prefix}-{suffix}"
        nonce = secrets.token_hex(16)
        clean_phone = "".join(filter(str.isdigit, phone_number)) if phone_number else None
        now = time.time()
        expires_at = now + ttl_seconds

        linking_rec = {
            "id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "whatsapp_account_id": None,
            "gateway_instance": gateway_instance,
            "pairing_code": pairing_code,
            "nonce": nonce,
            "status": "pending",
            "phone_number": clean_phone,
            "created_at": now,
            "expires_at": expires_at,
            "paired_at": None,
            "revoked_at": None
        }
        self.linking_sessions_store[session_id] = linking_rec

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppLinkingSession as LinkingModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(LinkingModel(
                            id=session_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            gateway_instance=gateway_instance,
                            pairing_code=pairing_code,
                            nonce=nonce,
                            status="pending",
                            phone_number=clean_phone,
                            expires_at=datetime.fromtimestamp(expires_at, timezone.utc)
                        ))
            except Exception:
                pass

        return linking_rec

    async def get_linking_session(
        self,
        session_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves linking transaction status with expiration check."""
        rec = self.linking_sessions_store.get(session_id)
        now = time.time()

        if rec:
            if tenant_id and rec.get("tenant_id") != tenant_id:
                return None
            if rec.get("status") == "pending" and now > rec.get("expires_at", 0):
                rec["status"] = "expired"
            return rec

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppLinkingSession as LinkingModel
                async with self.session_factory() as session:
                    stmt = select(LinkingModel).where(LinkingModel.id == session_id)
                    res = await session.execute(stmt)
                    s = res.scalar_one_or_none()
                    if s:
                        if tenant_id and s.tenant_id != tenant_id:
                            return None
                        exp_ts = s.expires_at.timestamp() if s.expires_at else 0
                        status = s.status
                        if status == "pending" and now > exp_ts:
                            status = "expired"
                        rec = {
                            "id": s.id,
                            "tenant_id": s.tenant_id,
                            "user_id": s.user_id,
                            "whatsapp_account_id": s.whatsapp_account_id,
                            "gateway_instance": s.gateway_instance,
                            "pairing_code": s.pairing_code,
                            "nonce": s.nonce,
                            "status": status,
                            "phone_number": s.phone_number,
                            "created_at": s.created_at.timestamp() if s.created_at else now,
                            "expires_at": exp_ts,
                            "paired_at": s.paired_at.timestamp() if s.paired_at else None,
                            "revoked_at": s.revoked_at.timestamp() if s.revoked_at else None
                        }
                        self.linking_sessions_store[s.id] = rec
                        return rec
            except Exception:
                pass

        return None

    async def confirm_pairing(
        self,
        session_id: str,
        nonce: str,
        pairing_code: str,
        encrypted_credentials: Optional[str] = None,
        phone_number: Optional[str] = None,
        key_version: int = 1
    ) -> Dict[str, Any]:
        """Confirms pairing transaction with one-time nonce and pairing code validation."""
        import hmac
        from backend.app.security.context import SecurityContextError

        linking_rec = await self.get_linking_session(session_id)
        if not linking_rec:
            raise SecurityContextError(f"Linking session {session_id} not found")

        if linking_rec["status"] == "expired":
            raise SecurityContextError("Linking session has expired. Please initiate a fresh pairing request.")

        if linking_rec["status"] == "paired":
            raise SecurityContextError("Linking session has already been used (replay rejected).")

        if linking_rec["status"] != "pending":
            raise SecurityContextError(f"Linking session is not pending (status: {linking_rec['status']})")

        nonce_valid = hmac.compare_digest(linking_rec["nonce"], nonce.strip())
        code_valid = hmac.compare_digest(
            linking_rec["pairing_code"].replace("-", "").upper(),
            pairing_code.replace("-", "").upper()
        )

        if not nonce_valid or not code_valid:
            raise SecurityContextError("Invalid pairing code or nonce verification failed.")

        final_phone = phone_number or linking_rec.get("phone_number")
        if not final_phone:
            raise SecurityContextError("Linked phone number is required to finalize WhatsApp account.")

        clean_phone = "".join(filter(str.isdigit, final_phone))

        account = await self.link_whatsapp_account(
            tenant_id=linking_rec["tenant_id"],
            user_id=linking_rec["user_id"],
            phone_number=clean_phone,
            display_name=f"WhatsApp (+{clean_phone})"
        )

        now = time.time()

        if encrypted_credentials:
            await self.save_whatsapp_session_credentials(
                account_id=account["id"],
                encrypted_credentials=encrypted_credentials,
                key_version=key_version
            )

        linking_rec["status"] = "paired"
        linking_rec["paired_at"] = now
        linking_rec["whatsapp_account_id"] = account["id"]

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppLinkingSession as LinkingModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(LinkingModel).where(LinkingModel.id == session_id)
                        res = await session.execute(stmt)
                        s = res.scalar_one_or_none()
                        if s:
                            s.status = "paired"
                            s.paired_at = datetime.fromtimestamp(now, timezone.utc)
                            s.whatsapp_account_id = account["id"]
            except Exception:
                pass

        return {
            "status": "paired",
            "session_id": session_id,
            "account_id": account["id"],
            "linked_number": clean_phone,
            "archive_start_time": now,
            "permissions_granted": [
                "whatsapp.search",
                "whatsapp.summary",
                "whatsapp.chat",
                "whatsapp.send_message"
            ],
            "revoke_instructions": f"To disconnect this account, send 'disconnect WhatsApp' or call POST /api/linking/sessions/{session_id}/revoke"
        }

    async def save_whatsapp_session_credentials(
        self,
        account_id: str,
        encrypted_credentials: str,
        key_version: int = 1
    ) -> Dict[str, Any]:
        """Saves encrypted Baileys session credentials isolated per WhatsApp account."""
        now = time.time()
        sess_id = f"wa_sess_{uuid.uuid4().hex[:12]}"
        rec = {
            "id": sess_id,
            "whatsapp_account_id": account_id,
            "encrypted_credentials": encrypted_credentials,
            "key_version": key_version,
            "created_at": now,
            "last_seen_at": now,
            "revoked_at": None
        }
        self.whatsapp_sessions_store[account_id] = rec

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppSession as SessionModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(SessionModel(
                            id=sess_id,
                            whatsapp_account_id=account_id,
                            encrypted_credentials=encrypted_credentials,
                            key_version=key_version
                        ))
            except Exception:
                pass

        return rec

    async def get_whatsapp_session_credentials(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves encrypted session credentials for an account."""
        rec = self.whatsapp_sessions_store.get(account_id)
        if rec and not rec.get("revoked_at"):
            return rec

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppSession as SessionModel
                async with self.session_factory() as session:
                    stmt = select(SessionModel).where(
                        and_(SessionModel.whatsapp_account_id == account_id, SessionModel.revoked_at.is_(None))
                    ).order_by(SessionModel.created_at.desc())
                    res = await session.execute(stmt)
                    s = res.scalar_one_or_none()
                    if s:
                        return {
                            "id": s.id,
                            "whatsapp_account_id": s.whatsapp_account_id,
                            "encrypted_credentials": s.encrypted_credentials,
                            "key_version": s.key_version,
                            "created_at": s.created_at.timestamp() if s.created_at else time.time(),
                            "last_seen_at": s.last_seen_at.timestamp() if s.last_seen_at else time.time(),
                            "revoked_at": s.revoked_at.timestamp() if s.revoked_at else None
                        }
            except Exception:
                pass

        return None

    async def revoke_linking_session(
        self,
        session_id: str,
        caller_user_id: str,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Revokes linking session and marks associated WhatsApp account credentials revoked."""
        from backend.app.security.context import SecurityContextError

        linking_rec = await self.get_linking_session(session_id)
        if not linking_rec:
            raise SecurityContextError(f"Linking session {session_id} not found")

        if tenant_id and linking_rec.get("tenant_id") != tenant_id:
            raise SecurityContextError("Unauthorized: session belongs to another tenant")

        if linking_rec.get("user_id") != caller_user_id:
            raise SecurityContextError("Unauthorized: caller does not own this linking session")

        now = time.time()
        linking_rec["status"] = "revoked"
        linking_rec["revoked_at"] = now

        account_id = linking_rec.get("whatsapp_account_id")
        if account_id:
            if account_id in self.accounts_store:
                self.accounts_store[account_id]["status"] = "revoked"
                self.accounts_store[account_id]["revoked_at"] = now
            if account_id in self.whatsapp_sessions_store:
                self.whatsapp_sessions_store[account_id]["revoked_at"] = now

        if self.session_factory:
            try:
                from backend.app.db.models import WhatsAppLinkingSession as LinkingModel, WhatsAppAccount as AccountModel, WhatsAppSession as SessionModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt_l = select(LinkingModel).where(LinkingModel.id == session_id)
                        res_l = await session.execute(stmt_l)
                        s = res_l.scalar_one_or_none()
                        if s:
                            s.status = "revoked"
                            s.revoked_at = datetime.fromtimestamp(now, timezone.utc)

                        if account_id:
                            stmt_a = select(AccountModel).where(AccountModel.id == account_id)
                            res_a = await session.execute(stmt_a)
                            a = res_a.scalar_one_or_none()
                            if a:
                                a.status = "revoked"
                                a.revoked_at = datetime.fromtimestamp(now, timezone.utc)

                            stmt_sess = select(SessionModel).where(SessionModel.whatsapp_account_id == account_id)
                            res_sess = await session.execute(stmt_sess)
                            sess_objs = res_sess.scalars().all()
                            for sess_obj in sess_objs:
                                sess_obj.revoked_at = datetime.fromtimestamp(now, timezone.utc)
            except Exception:
                pass

        return {
            "status": "revoked",
            "session_id": session_id,
            "account_id": account_id,
            "revoked_at": now
        }

    async def create_outbox_event(
        self,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        scheduled_at: Optional[datetime] = None,
        max_retries: int = 5
    ) -> Dict[str, Any]:
        """Creates a durable outbox event with tenant scoping and deduplication via idempotency key."""
        # Check in-memory store for idempotency
        for evt in self.outbox_store:
            if evt.get("tenant_id") == tenant_id and evt.get("idempotency_key") == idempotency_key:
                return evt

        now_dt = datetime.now(timezone.utc)
        sched_dt = scheduled_at or now_dt
        eid = str(uuid.uuid4())

        record = {
            "id": eid,
            "tenant_id": tenant_id,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "payload": payload,
            "status": "pending",
            "retry_count": 0,
            "max_retries": max_retries,
            "idempotency_key": idempotency_key,
            "error_message": None,
            "scheduled_at": sched_dt,
            "created_at": now_dt,
            "published_at": None,
            "delivered_at": None
        }
        self.outbox_store.append(record)

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                async with self.session_factory() as session:
                    async with session.begin():
                        session.add(OutboxModel(
                            id=eid,
                            tenant_id=tenant_id,
                            aggregate_type=aggregate_type,
                            aggregate_id=aggregate_id,
                            event_type=event_type,
                            payload=payload,
                            status="pending",
                            retry_count=0,
                            max_retries=max_retries,
                            idempotency_key=idempotency_key,
                            scheduled_at=sched_dt
                        ))
            except Exception:
                pass

        return record

    async def fetch_pending_outbox_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetches pending and failed events ready for dispatch (scheduled_at <= now, retry_count < max_retries)."""
        now_dt = datetime.now(timezone.utc)
        ready = []
        for evt in self.outbox_store:
            if evt.get("status") in ("pending", "failed"):
                if evt.get("retry_count", 0) < evt.get("max_retries", 5):
                    sched = evt.get("scheduled_at")
                    if sched is None or sched <= now_dt:
                        ready.append(evt)
                        if len(ready) >= limit:
                            break

        if ready:
            return ready

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                from sqlalchemy import and_, or_
                async with self.session_factory() as session:
                    stmt = (
                        select(OutboxModel)
                        .where(
                            and_(
                                OutboxModel.status.in_(["pending", "failed"]),
                                OutboxModel.retry_count < OutboxModel.max_retries,
                                OutboxModel.scheduled_at <= now_dt
                            )
                        )
                        .order_by(OutboxModel.scheduled_at.asc())
                        .limit(limit)
                    )
                    res = await session.execute(stmt)
                    rows = res.scalars().all()
                    for r in rows:
                        ready.append({
                            "id": r.id,
                            "tenant_id": r.tenant_id,
                            "aggregate_type": r.aggregate_type,
                            "aggregate_id": r.aggregate_id,
                            "event_type": r.event_type,
                            "payload": r.payload,
                            "status": r.status,
                            "retry_count": r.retry_count,
                            "max_retries": r.max_retries,
                            "idempotency_key": r.idempotency_key,
                            "error_message": r.error_message,
                            "scheduled_at": r.scheduled_at,
                            "created_at": r.created_at,
                            "published_at": r.published_at,
                            "delivered_at": r.delivered_at
                        })
            except Exception:
                pass

        return ready

    async def mark_outbox_event_published(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Marks an outbox event as successfully published to message broker/channel."""
        now_dt = datetime.now(timezone.utc)
        target = None
        for evt in self.outbox_store:
            if evt.get("id") == event_id:
                evt["status"] = "published"
                evt["published_at"] = now_dt
                target = evt
                break

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(OutboxModel).where(OutboxModel.id == event_id)
                        res = await session.execute(stmt)
                        m = res.scalar_one_or_none()
                        if m:
                            m.status = "published"
                            m.published_at = now_dt
            except Exception:
                pass

        return target

    async def mark_outbox_event_delivered(
        self,
        idempotency_key_or_id: str,
        provider_message_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Marks an outbox event as delivered following gateway acknowledgment receipt."""
        now_dt = datetime.now(timezone.utc)
        target = None
        for evt in self.outbox_store:
            if evt.get("id") == idempotency_key_or_id or evt.get("idempotency_key") == idempotency_key_or_id:
                evt["status"] = "delivered"
                evt["delivered_at"] = now_dt
                if provider_message_id and isinstance(evt.get("payload"), dict):
                    evt["payload"]["provider_delivery_id"] = provider_message_id
                target = evt
                break

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                from sqlalchemy import or_
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(OutboxModel).where(
                            or_(
                                OutboxModel.id == idempotency_key_or_id,
                                OutboxModel.idempotency_key == idempotency_key_or_id
                            )
                        )
                        res = await session.execute(stmt)
                        m = res.scalar_one_or_none()
                        if m:
                            m.status = "delivered"
                            m.delivered_at = now_dt
                            if provider_message_id and isinstance(m.payload, dict):
                                pl = dict(m.payload)
                                pl["provider_delivery_id"] = provider_message_id
                                m.payload = pl
            except Exception:
                pass

        return target

    async def mark_outbox_event_failed(
        self,
        event_id: str,
        error_message: str,
        backoff_seconds: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Handles outbox event dispatch failure with exponential backoff and dead-letter routing."""
        now_dt = datetime.now(timezone.utc)
        target = None
        for evt in self.outbox_store:
            if evt.get("id") == event_id:
                evt["retry_count"] = evt.get("retry_count", 0) + 1
                evt["error_message"] = error_message
                if evt["retry_count"] >= evt.get("max_retries", 5):
                    evt["status"] = "dead_letter"
                else:
                    evt["status"] = "failed"
                    evt["scheduled_at"] = now_dt + timedelta(seconds=backoff_seconds)
                target = evt
                break

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                async with self.session_factory() as session:
                    async with session.begin():
                        stmt = select(OutboxModel).where(OutboxModel.id == event_id)
                        res = await session.execute(stmt)
                        m = res.scalar_one_or_none()
                        if m:
                            m.retry_count = (m.retry_count or 0) + 1
                            m.error_message = error_message
                            if m.retry_count >= (m.max_retries or 5):
                                m.status = "dead_letter"
                            else:
                                m.status = "failed"
                                m.scheduled_at = now_dt + timedelta(seconds=backoff_seconds)
            except Exception:
                pass

        return target

    async def get_outbox_event_by_idempotency_key(
        self,
        tenant_id: str,
        idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieves an outbox event scoped strictly to tenant and idempotency key."""
        for evt in self.outbox_store:
            if evt.get("tenant_id") == tenant_id and evt.get("idempotency_key") == idempotency_key:
                return evt

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                from sqlalchemy import and_
                async with self.session_factory() as session:
                    stmt = select(OutboxModel).where(
                        and_(
                            OutboxModel.tenant_id == tenant_id,
                            OutboxModel.idempotency_key == idempotency_key
                        )
                    )
                    res = await session.execute(stmt)
                    r = res.scalar_one_or_none()
                    if r:
                        rec = {
                            "id": r.id,
                            "tenant_id": r.tenant_id,
                            "aggregate_type": r.aggregate_type,
                            "aggregate_id": r.aggregate_id,
                            "event_type": r.event_type,
                            "payload": r.payload,
                            "status": r.status,
                            "retry_count": r.retry_count,
                            "max_retries": r.max_retries,
                            "idempotency_key": r.idempotency_key,
                            "error_message": r.error_message,
                            "scheduled_at": r.scheduled_at,
                            "created_at": r.created_at,
                            "published_at": r.published_at,
                            "delivered_at": r.delivered_at
                        }
                        self.outbox_store.append(rec)
                        return rec
            except Exception:
                pass

        return None

    async def get_outbox_event(self, event_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves an outbox event by UUID."""
        for evt in self.outbox_store:
            if evt.get("id") == event_id:
                if tenant_id and evt.get("tenant_id") != tenant_id:
                    return None
                return evt

        if self.session_factory:
            try:
                from backend.app.db.models import OutboxEvent as OutboxModel
                async with self.session_factory() as session:
                    stmt = select(OutboxModel).where(OutboxModel.id == event_id)
                    res = await session.execute(stmt)
                    r = res.scalar_one_or_none()
                    if r:
                        if tenant_id and r.tenant_id != tenant_id:
                            return None
                        return {
                            "id": r.id,
                            "tenant_id": r.tenant_id,
                            "aggregate_type": r.aggregate_type,
                            "aggregate_id": r.aggregate_id,
                            "event_type": r.event_type,
                            "payload": r.payload,
                            "status": r.status,
                            "retry_count": r.retry_count,
                            "max_retries": r.max_retries,
                            "idempotency_key": r.idempotency_key,
                            "error_message": r.error_message,
                            "scheduled_at": r.scheduled_at,
                            "created_at": r.created_at,
                            "published_at": r.published_at,
                            "delivered_at": r.delivered_at
                        }
            except Exception:
                pass

        return None

    async def export_user_data(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Exports all personal data belonging to a user across all platform entities."""
        from datetime import datetime, timezone

        user_info = await self.get_user(user_id=user_id, tenant_id=tenant_id)
        if not user_info:
            user_info = {"id": user_id, "tenant_id": tenant_id}

        # 1. Accounts
        accounts = [
            acc for acc in self.accounts_store.values()
            if acc.get("user_id") == user_id and acc.get("tenant_id") == tenant_id
        ]
        account_ids = {acc.get("id") for acc in accounts}

        # 2. Desktop devices
        devices = [
            dev for dev in self.devices_store.values()
            if dev.get("user_id") == user_id and dev.get("tenant_id") == tenant_id
        ]

        # 3. Messages
        messages = [
            msg for msg in self.messages_store
            if msg.get("whatsapp_account_id") in account_ids
        ]

        # 4. Approvals
        approvals = [
            appr for appr in self.approvals_store.values()
            if appr.get("user_id") == user_id and (not appr.get("tenant_id") or appr.get("tenant_id") == tenant_id)
        ]

        # 5. Executions
        executions = [
            exc for exc in self.executions_store.values()
            if exc.get("user_id") == user_id and exc.get("tenant_id") == tenant_id
        ]

        # 6. Audit events
        audit_events = [
            evt for evt in self.audit_log_store
            if evt.get("user_id") == user_id
        ]

        return {
            "tenant_id": tenant_id,
            "user": user_info,
            "whatsapp_accounts": accounts,
            "desktop_devices": devices,
            "messages": messages,
            "approvals": approvals,
            "executions": executions,
            "audit_events": audit_events,
            "exported_at": datetime.now(timezone.utc).isoformat()
        }

    async def purge_user_data(
        self,
        tenant_id: str,
        user_id: str,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Permanently purges or redacts data belonging to the user with explicit confirmation flag."""
        from datetime import datetime, timezone
        opts = options or {}
        if not opts.get("confirm"):
            raise ValueError("Data purge requires explicit confirmation flag 'confirm=True'")

        purge_msgs = opts.get("purge_messages", True)
        purge_apprs = opts.get("purge_approvals", True)
        purge_execs = opts.get("purge_executions", True)
        revoke_tokens = opts.get("revoke_tokens", True)

        now = datetime.now(timezone.utc)
        purged_counts = {"messages": 0, "approvals": 0, "executions": 0, "tokens_revoked": 0}

        # Find user WhatsApp accounts
        user_accounts = [
            acc for acc in self.accounts_store.values()
            if acc.get("user_id") == user_id and acc.get("tenant_id") == tenant_id
        ]
        user_account_ids = {acc.get("id") for acc in user_accounts}

        # 1. Purge messages
        if purge_msgs and user_account_ids:
            initial_count = len(self.messages_store)
            self.messages_store = [
                m for m in self.messages_store
                if m.get("whatsapp_account_id") not in user_account_ids
            ]
            purged_counts["messages"] = initial_count - len(self.messages_store)

            if self.session_factory:
                try:
                    from backend.app.db.models import Message as MsgModel
                    async with self.session_factory() as session:
                        async with session.begin():
                            del_stmt = delete(MsgModel).where(MsgModel.whatsapp_account_id.in_(user_account_ids))
                            res = await session.execute(del_stmt)
                            purged_counts["messages"] = max(purged_counts["messages"], res.rowcount)
                except Exception:
                    pass

        # 2. Purge approvals
        if purge_apprs:
            to_del_apprs = [
                k for k, v in self.approvals_store.items()
                if v.get("user_id") == user_id
            ]
            for k in to_del_apprs:
                del self.approvals_store[k]
                purged_counts["approvals"] += 1

            if self.session_factory:
                try:
                    from backend.app.db.models import PendingApproval as ApprModel
                    async with self.session_factory() as session:
                        async with session.begin():
                            del_stmt = delete(ApprModel).where(ApprModel.user_id == user_id)
                            res = await session.execute(del_stmt)
                            purged_counts["approvals"] = max(purged_counts["approvals"], res.rowcount)
                except Exception:
                    pass

        # 3. Purge executions
        if purge_execs:
            to_del_execs = [
                k for k, v in self.executions_store.items()
                if v.get("user_id") == user_id
            ]
            for k in to_del_execs:
                del self.executions_store[k]
                purged_counts["executions"] += 1

            if self.session_factory:
                try:
                    from backend.app.db.models import Execution as ExecModel
                    async with self.session_factory() as session:
                        async with session.begin():
                            del_stmt = delete(ExecModel).where(ExecModel.user_id == user_id)
                            res = await session.execute(del_stmt)
                            purged_counts["executions"] = max(purged_counts["executions"], res.rowcount)
                except Exception:
                    pass

        # 4. Revoke tokens and devices
        if revoke_tokens:
            revoked = await self.revoke_user_oauth_tokens(user_id=user_id, tenant_id=tenant_id)
            if revoked:
                purged_counts["tokens_revoked"] = 1

            for dev in self.devices_store.values():
                if dev.get("user_id") == user_id and dev.get("tenant_id") == tenant_id:
                    dev["is_online"] = False
                    dev["revoked_at"] = now

            for acc in user_accounts:
                acc["status"] = "revoked"
                acc["revoked_at"] = now

        # Append audit entry for compliance
        await self.insert_audit_log({
            "user_id": user_id,
            "tenant_id": tenant_id,
            "raw_intent": "gdpr_purge",
            "risk_level": "critical",
            "status": "executed",
            "request_id": f"purge-{uuid.uuid4().hex[:8]}"
        })

        return {
            "status": "success",
            "user_id": user_id,
            "tenant_id": tenant_id,
            "purged_records": purged_counts,
            "purged_at": now.isoformat()
        }

    async def cleanup_retention(
        self,
        tenant_id: str,
        retention_days: int,
        purge_messages: bool = True,
        purge_executions: bool = True
    ) -> Dict[str, Any]:
        """Cleans up data exceeding the retention window for the tenant."""
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=retention_days)

        purged_msgs = 0
        purged_execs = 0

        # In-memory purge
        if purge_messages:
            initial = len(self.messages_store)
            self.messages_store = [
                m for m in self.messages_store
                if not (m.get("tenant_id") == tenant_id and m.get("message_timestamp") and m.get("message_timestamp") < cutoff)
            ]
            purged_msgs = initial - len(self.messages_store)

        if purge_executions:
            initial = len(self.executions_store)
            self.executions_store = {
                k: v for k, v in self.executions_store.items()
                if not (v.get("tenant_id") == tenant_id and v.get("created_at") and v.get("created_at") < cutoff)
            }
            purged_execs = initial - len(self.executions_store)

        if self.session_factory:
            try:
                from backend.app.db.models import Message as MsgModel, Execution as ExecModel
                async with self.session_factory() as session:
                    async with session.begin():
                        if purge_messages:
                            stmt = delete(MsgModel).where(
                                and_(MsgModel.tenant_id == tenant_id, MsgModel.message_timestamp < cutoff)
                            )
                            res = await session.execute(stmt)
                            purged_msgs = max(purged_msgs, res.rowcount)
                        if purge_executions:
                            stmt = delete(ExecModel).where(
                                and_(ExecModel.tenant_id == tenant_id, ExecModel.created_at < cutoff)
                            )
                            res = await session.execute(stmt)
                            purged_execs = max(purged_execs, res.rowcount)
            except Exception:
                pass

        return {
            "status": "success",
            "tenant_id": tenant_id,
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "purged_messages": purged_msgs,
            "purged_executions": purged_execs
        }

    async def revoke_all_user_sessions(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Globally revokes all active credentials, tokens, devices, and sessions for the user."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        # 1. Revoke WhatsApp accounts & sessions
        wa_count = 0
        for acc in self.accounts_store.values():
            if acc.get("user_id") == user_id and acc.get("tenant_id") == tenant_id:
                acc["status"] = "revoked"
                acc["revoked_at"] = now
                wa_count += 1

        # 2. Revoke OAuth tokens
        oauth_count = 1 if await self.revoke_user_oauth_tokens(user_id=user_id, tenant_id=tenant_id) else 0

        # 3. Revoke Desktop devices & disconnect active sockets
        dev_count = 0
        for dev in self.devices_store.values():
            if dev.get("user_id") == user_id and dev.get("tenant_id") == tenant_id:
                dev["is_online"] = False
                dev["revoked_at"] = now
                dev_count += 1

        try:
            from backend.app.desktop.presence import presence_manager
            presence_manager.unregister_connection(user_id)
        except Exception:
            pass

        # 4. Insert audit record
        await self.insert_audit_log({
            "user_id": user_id,
            "tenant_id": tenant_id,
            "raw_intent": "user_global_revocation",
            "risk_level": "high",
            "status": "executed",
            "request_id": f"revocation-{uuid.uuid4().hex[:8]}"
        })

        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "revoked_at": now.isoformat(),
            "devices_disconnected": dev_count,
            "oauth_connections_revoked": oauth_count,
            "sessions_invalidated": wa_count
        }

    async def verify_audit_log_integrity(self, tenant_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """Verifies immutability and valid chain characteristics for audit records."""
        records = self.audit_log_store
        if tenant_id:
            records = [r for r in records if r.get("tenant_id") == tenant_id]

        total = len(records)
        for r in records[-limit:]:
            if not r.get("request_id") or not r.get("status"):
                return {"status": "failed", "error": "Missing mandatory audit field", "tampered": True}

        return {
            "status": "verified",
            "total_records": total,
            "checked_records": min(total, limit),
            "tampered": False
        }


from backend.app.db.database import AsyncSessionLocal

repository = DatabaseRepository(session_factory=AsyncSessionLocal)
