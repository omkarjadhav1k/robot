"""Immutable audit trail model for security and compliance."""

import enum
from sqlalchemy import Column, Enum, JSON, String
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ActorType(str, enum.Enum):
    """Originator of a recorded action."""
    USER = "USER"
    ROBOT = "ROBOT"
    AI = "AI"
    SYSTEM = "SYSTEM"


class AuditLog(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Immutable audit entry for state mutations and security events."""
    __tablename__ = "audit_logs"

    actor_type = Column(Enum(ActorType), nullable=False)
    actor_id = Column(String(100), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)

    # Relationships
    business = relationship("Business", back_populates="audit_logs")
