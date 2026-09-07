"""Dynamic AI Tasks and Reminder model."""

import enum
from datetime import datetime
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TaskType(str, enum.Enum):
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    CUSTOMER_FOLLOWUP = "CUSTOMER_FOLLOWUP"
    STOCK_REMINDER = "STOCK_REMINDER"
    BUSINESS_TASK = "BUSINESS_TASK"
    OWNER_REMINDER = "OWNER_REMINDER"
    CUSTOM = "CUSTOM"


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class AITask(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Structured, persistent operational tasks extracted from natural conversation or created by owner."""
    __tablename__ = "ai_tasks"

    task_type = Column(Enum(TaskType), nullable=False, default=TaskType.CUSTOM, index=True)
    description = Column(Text, nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, nullable=False, default=3)  # 1 (lowest) to 5 (highest)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(50), nullable=False, default="MAX")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    task_metadata = Column(JSON, nullable=True)

    # Relationships
    business = relationship("Business", back_populates="ai_tasks")
    customer = relationship("Customer", backref="ai_tasks")
