"""Dynamic AI Memory model for contextual facts, preferences, and operating habits."""

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIMemory(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Dynamic AI memory for non-authoritative contextual knowledge, owner habits,
    and customer preferences. Strictly isolated from PostgreSQL business truth.
    """
    __tablename__ = "ai_memory"

    memory_type = Column(String(50), nullable=False, default="BUSINESS_PREFERENCE", index=True)
    content = Column(Text, nullable=False)
    importance = Column(Integer, nullable=False, default=5)  # Scale 1-10
    source = Column(String(50), nullable=False, default="CONVERSATION")
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    business = relationship("Business", back_populates="ai_memories")
