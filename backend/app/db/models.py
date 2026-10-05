"""SQLAlchemy Models for FastAgent."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Boolean, Float, Integer, DateTime, JSON, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from backend.app.db.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(32), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    pending_approvals = relationship("PendingApproval", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")
    policy = relationship("UserPolicy", back_populates="user", uselist=False, cascade="all, delete-orphan")


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
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
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
