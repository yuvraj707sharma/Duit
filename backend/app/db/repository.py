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
        self.executions_store: Dict[str, Dict[str, Any]] = {}
        self.messages_store: List[Dict[str, Any]] = []
        self.approvals_store: Dict[str, Dict[str, Any]] = {}
        self.audit_log_store: List[Dict[str, Any]] = []
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        self.webhook_dedupe_store: Dict[str, Dict[str, Any]] = {}
        self.tokens_store: Dict[str, Dict[str, Any]] = {}
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
        sender_phone: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Searches archived messages strictly isolated to tenant and linked WhatsApp account."""
        results = []
        clean_filter_phone = "".join(filter(str.isdigit, sender_phone)) if sender_phone else None
        q_lower = query_text.lower().strip() if query_text else None

        for m in self.messages_store:
            # Strict tenant and account boundary
            if m.get("tenant_id") != tenant_id or m.get("whatsapp_account_id") != whatsapp_account_id:
                continue

            if clean_filter_phone and clean_filter_phone not in (m.get("sender_phone") or ""):
                continue

            if q_lower and q_lower not in m.get("text", "").lower():
                continue

            results.append(m)
            if len(results) >= limit:
                break

        return results

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


from backend.app.db.database import AsyncSessionLocal

repository = DatabaseRepository(session_factory=AsyncSessionLocal)
