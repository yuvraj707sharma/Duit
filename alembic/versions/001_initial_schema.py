"""Initial schema migration for DUIT relational tables.

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-11-07 22:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tenants
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(64), unique=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )

    # 2. Users
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id', ondelete='CASCADE'), index=True),
        sa.Column('phone_number', sa.String(32), unique=True, index=True),
        sa.Column('email', sa.String(255), unique=True, index=True),
        sa.Column('full_name', sa.String(255)),
        sa.Column('role', sa.String(32), default='member', nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('updated_at', sa.DateTime(timezone=True)),
    )

    # 3. WhatsApp Accounts
    op.create_table(
        'whatsapp_accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('phone_number', sa.String(32), index=True, nullable=False),
        sa.Column('display_name', sa.String(150)),
        sa.Column('status', sa.String(32), default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('last_seen_at', sa.DateTime(timezone=True)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
    )

    # 4. Pending Approvals
    op.create_table(
        'pending_approvals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id', ondelete='CASCADE'), index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('action_type', sa.String(64), nullable=False),
        sa.Column('idempotency_key', sa.String(64), unique=True, index=True, nullable=False),
        sa.Column('action_payload', sa.JSON(), nullable=False),
        sa.Column('risk_level', sa.String(16), default='medium', nullable=False),
        sa.Column('confidence', sa.Float(), default=0.0, nullable=False),
        sa.Column('status', sa.String(24), default='pending', nullable=False),
        sa.Column('reasoning_tag', sa.String(255)),
        sa.Column('version', sa.Integer(), default=1, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
    )

    # 5. Outbox Events
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('aggregate_type', sa.String(64), nullable=False),
        sa.Column('aggregate_id', sa.String(64), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(24), default='pending', nullable=False),
        sa.Column('retry_count', sa.Integer(), default=0, nullable=False),
        sa.Column('max_retries', sa.Integer(), default=5, nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=False),
        sa.Column('error_message', sa.Text()),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
        sa.Column('published_at', sa.DateTime(timezone=True)),
        sa.Column('delivered_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('tenant_id', 'idempotency_key', name='uq_outbox_tenant_idempotency'),
    )

    # 6. Audit Logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id', ondelete='CASCADE'), index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('account_id', sa.String(36), index=True),
        sa.Column('device_id', sa.String(36), index=True),
        sa.Column('execution_id', sa.String(36), index=True),
        sa.Column('request_id', sa.String(64), index=True, nullable=False),
        sa.Column('raw_intent', sa.String(64), nullable=False),
        sa.Column('risk_level', sa.String(16), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('tools_called', sa.JSON(), nullable=False),
        sa.Column('was_confirmed', sa.Boolean(), default=False, nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('stage_latencies_ms', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('outbox_events')
    op.drop_table('pending_approvals')
    op.drop_table('whatsapp_accounts')
    op.drop_table('users')
    op.drop_table('tenants')
