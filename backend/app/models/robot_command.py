"""Robot command lifecycle and AI activity tracking models."""

import enum
from sqlalchemy import Column, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CommandStatus(str, enum.Enum):
    """Lifecycle states for hardware commands dispatched to the ESP32."""
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    SENT = "SENT"
    RECEIVED = "RECEIVED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RobotCommand(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Individual command dispatched to a physical robot with strict lifecycle tracking."""
    __tablename__ = "robot_commands"

    command_id = Column(String(50), unique=True, nullable=False, index=True)
    robot_id = Column(UUID(as_uuid=True), ForeignKey("robots.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False, default=lambda: {})
    status = Column(Enum(CommandStatus), nullable=False, default=CommandStatus.PENDING)
    result_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    robot = relationship("RobotDevice", back_populates="commands")


class AIActivity(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Audit log of natural language conversations and tool actions executed by Gemini."""
    __tablename__ = "ai_activity"

    robot_id = Column(String(50), nullable=True, index=True)
    user_query = Column(Text, nullable=False)
    ai_response_text = Column(Text, nullable=False)
    structured_tool_name = Column(String(50), nullable=True)
    structured_tool_payload = Column(JSON, nullable=True)
    execution_status = Column(String(20), nullable=False, default="SUCCESS")
    latency_ms = Column(Integer, nullable=True)
