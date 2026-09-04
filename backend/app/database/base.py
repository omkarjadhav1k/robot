"""SQLAlchemy Declarative Base and common model mixins."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Root declarative base for all database models."""
    pass


class TimestampMixin:
    """Provides automatic UTC timestamps for entity creation and updates."""
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """Provides a UUID primary key for secure, unguessable IDs."""
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TenantMixin:
    """Enforces multi-tenant isolation by binding records to a business entity."""
    @declared_attr
    def business_id(cls):
        return Column(
            UUID(as_uuid=True),
            ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
