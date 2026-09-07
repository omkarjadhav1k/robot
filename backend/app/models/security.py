"""Owner verification, PIN security, and security audit event models."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OwnerSecurity(Base, TenantMixin, TimestampMixin):
    """Secure store for business owner PIN hash and lockout state."""
    __tablename__ = "owner_security"

    id = Column(UUID(as_uuid=True), primary_key=True, default=UUIDPrimaryKeyMixin.id.default.arg)
    pin_hash = Column(String(255), nullable=False)
    failed_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    business = relationship("Business", back_populates="owner_security")


class SecurityEvent(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Immutable audit trail for authorization attempts and high-risk actions."""
    __tablename__ = "security_events"

    robot_id = Column(String(50), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    success = Column(Boolean, nullable=False, default=True)
    event_timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    event_metadata = Column(JSON, nullable=True)  # Strictly sanitized, NEVER contains raw PIN

    # Relationships
    business = relationship("Business", back_populates="security_events")
