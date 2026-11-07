"""SQLAlchemy Models for FastAgent & DUIT."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Boolean, Float, Integer, DateTime, JSON, Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    slug = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    whatsapp_accounts = relationship("WhatsAppAccount", back_populates="tenant", cascade="all, delete-orphan")
    desktop_devices = relationship("DesktopDevice", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="tenant", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    phone_number = Column(String(32), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(32), default="member", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant = relationship("Tenant", back_populates="users")
    whatsapp_accounts = relationship("WhatsAppAccount", back_populates="user", cascade="all, delete-orphan")
    desktop_devices = relationship("DesktopDevice", back_populates="user", cascade="all, delete-orphan")
    oauth_connections = relationship("OAuthConnection", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    executions = relationship("Execution", back_populates="user", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    pending_approvals = relationship("PendingApproval", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    policy = relationship("UserPolicy", back_populates="user", uselist=False, cascade="all, delete-orphan")


class WhatsAppAccount(Base):
    __tablename__ = "whatsapp_accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    phone_number = Column(String(32), nullable=False, index=True)
    display_name = Column(String(150), nullable=True)
    status = Column(String(32), nullable=False, default="active")  # active, disconnected, pending_pairing, revoked
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="whatsapp_accounts")
    user = relationship("User", back_populates="whatsapp_accounts")
    sessions = relationship("WhatsAppSession", back_populates="whatsapp_account", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="whatsapp_account", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_wa_account_tenant_phone", "tenant_id", "phone_number"),
    )


class WhatsAppSession(Base):
    __tablename__ = "whatsapp_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    whatsapp_account_id = Column(String(36), ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"), index=True, nullable=False)
    encrypted_credentials = Column(Text, nullable=False)
    key_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    whatsapp_account = relationship("WhatsAppAccount", back_populates="sessions")


class WhatsAppLinkingSession(Base):
    __tablename__ = "whatsapp_linking_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    whatsapp_account_id = Column(String(36), ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"), index=True, nullable=True)
    gateway_instance = Column(String(64), nullable=False, default="directorbot-primary")
    pairing_code = Column(String(32), index=True, nullable=True)
    nonce = Column(String(64), unique=True, index=True, nullable=False)
    status = Column(String(24), nullable=False, default="pending")  # pending, paired, expired, revoked
    phone_number = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    paired_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_linking_tenant_user_status", "tenant_id", "user_id", "status"),
    )


class DesktopDevice(Base):
    __tablename__ = "desktop_devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_name = Column(String(100), nullable=False)
    platform = Column(String(32), nullable=False, default="windows")  # windows, macos, linux
    public_key = Column(Text, nullable=True)
    is_online = Column(Boolean, nullable=False, default=False)
    permissions = Column(JSON, nullable=False, default=list)
    last_seen_at = Column(DateTime(timezone=True), default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="desktop_devices")
    user = relationship("User", back_populates="desktop_devices")
    executions = relationship("Execution", back_populates="device")

    __table_args__ = (
        Index("idx_device_tenant_user", "tenant_id", "user_id"),
    )


class OAuthConnection(Base):
    __tablename__ = "oauth_connections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(32), nullable=False, default="google")
    encrypted_access_token = Column(Text, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=True)
    scopes = Column(JSON, nullable=False, default=list)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="oauth_connections")

    __table_args__ = (
        Index("idx_oauth_tenant_user_provider", "tenant_id", "user_id", "provider"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    channel = Column(String(32), nullable=False, default="whatsapp")  # whatsapp, web, desktop
    external_chat_jid = Column(String(100), index=True, nullable=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    tenant = relationship("Tenant", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    whatsapp_account_id = Column(String(36), ForeignKey("whatsapp_accounts.id", ondelete="CASCADE"), index=True, nullable=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=True)
    provider_message_id = Column(String(150), index=True, nullable=False)
    sender_jid = Column(String(100), nullable=False)
    sender_phone = Column(String(50), nullable=True, index=True)
    sender_display_name = Column(String(150), nullable=True)
    direction = Column(String(16), nullable=False, default="inbound")  # inbound, outbound
    text = Column(Text, nullable=False)
    media_metadata = Column(JSON, nullable=True)
    message_timestamp = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), default=utc_now)
    content_hash = Column(String(64), nullable=True)

    tenant = relationship("Tenant", back_populates="messages")
    whatsapp_account = relationship("WhatsAppAccount", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        UniqueConstraint("whatsapp_account_id", "provider_message_id", name="uq_wa_account_provider_msg"),
        Index("idx_msg_account_timestamp", "whatsapp_account_id", "message_timestamp"),
        Index("idx_msg_account_sender", "whatsapp_account_id", "sender_jid", "message_timestamp"),
    )


class Execution(Base):
    __tablename__ = "executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id = Column(String(36), ForeignKey("desktop_devices.id", ondelete="SET NULL"), index=True, nullable=True)
    capability = Column(String(64), nullable=False)
    arguments = Column(JSON, nullable=False, default=dict)
    risk_level = Column(String(16), nullable=False, default="medium")
    status = Column(String(24), nullable=False, default="pending")  # pending, running, completed, failed, cancelled
    verified = Column(Boolean, nullable=False, default=False)
    output = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="executions")
    user = relationship("User", back_populates="executions")
    device = relationship("DesktopDevice", back_populates="executions")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(32), nullable=False, default="google")
    encrypted_access_token = Column(Text, nullable=False)
    encrypted_refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="oauth_tokens")


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    action_type = Column(String(64), nullable=False)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    action_payload = Column(JSON, nullable=False)
    risk_level = Column(String(16), nullable=False, default="medium")
    confidence = Column(Float, nullable=False, default=0.0)
    status = Column(String(24), nullable=False, default="pending")  # pending, approved, rejected, edited, superseded, expired
    reasoning_tag = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="pending_approvals")


class AuditLog(Base):
    """Insert-only audit log table."""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    account_id = Column(String(36), index=True, nullable=True)
    device_id = Column(String(36), index=True, nullable=True)
    execution_id = Column(String(36), index=True, nullable=True)
    request_id = Column(String(64), index=True, nullable=False)
    raw_intent = Column(String(64), nullable=False)
    risk_level = Column(String(16), nullable=False)
    confidence = Column(Float, nullable=False)
    tools_called = Column(JSON, nullable=False, default=list)
    was_confirmed = Column(Boolean, nullable=False, default=False)
    status = Column(String(24), nullable=False)  # executed, rejected, failed, pending_confirmation, direct_rule
    stage_latencies_ms = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="audit_logs")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    user_id = Column(String(36), index=True, nullable=False)
    idempotency_key = Column(String(64), unique=True, index=True, nullable=False)
    message_id = Column(String(64), index=True, nullable=True)
    action = Column(String(64), nullable=False)
    response_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class LearningCorrection(Base):
    __tablename__ = "learning_corrections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    query_text = Column(Text, nullable=False)
    predicted_intent = Column(String(64), nullable=False)
    user_action = Column(String(24), nullable=False)  # approve, edit, reject
    corrected_intent = Column(String(64), nullable=True)
    corrected_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)


class UserPolicy(Base):
    __tablename__ = "user_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    allowed_recipients = Column(JSON, nullable=False, default=list)
    auto_approve_thresholds = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    user = relationship("User", back_populates="policy")


class BetaRegistration(Base):
    __tablename__ = "beta_registrations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), index=True, nullable=False)
    phone_number = Column(String(32), index=True, nullable=False)
    status = Column(String(32), default="pending")  # pending, approved, rejected
    created_at = Column(DateTime(timezone=True), default=utc_now)


class WhatsAppSessionFile(Base):
    __tablename__ = "whatsapp_session_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(64), index=True, nullable=False)
    file_name = Column(String(255), index=True, nullable=False)
    file_content = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    aggregate_type = Column(String(64), index=True, nullable=False)
    aggregate_id = Column(String(64), index=True, nullable=False)
    event_type = Column(String(64), index=True, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(24), index=True, nullable=False, default="pending")
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=5)
    idempotency_key = Column(String(64), index=True, nullable=False)
    error_message = Column(Text, nullable=True)
    scheduled_at = Column(DateTime(timezone=True), index=True, default=utc_now)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    published_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_outbox_tenant_idempotency"),
        Index("ix_outbox_status_scheduled", "status", "scheduled_at"),
    )


class DesktopPairingSession(Base):
    __tablename__ = "desktop_pairing_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    pairing_code = Column(String(32), index=True, nullable=False)
    nonce = Column(String(64), unique=True, index=True, nullable=False)
    device_id = Column(String(36), ForeignKey("desktop_devices.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), index=True, nullable=False, default="pending")  # pending, claimed, expired, revoked
    created_at = Column(DateTime(timezone=True), default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=True)


class LocalJournalEntry(Base):
    __tablename__ = "local_journal_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id = Column(String(36), ForeignKey("desktop_devices.id", ondelete="CASCADE"), index=True, nullable=False)
    action = Column(String(64), nullable=False)
    arguments_hash = Column(String(64), nullable=True)
    status = Column(String(24), nullable=False, default="executed")  # executed, blocked, failed
    signature = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
