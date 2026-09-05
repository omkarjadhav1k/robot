"""Business instruction file model for customized operational context."""

from sqlalchemy import Boolean, Column, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessInstruction(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Uploaded .txt business guidelines providing context to the Gemini AI layer."""
    __tablename__ = "business_instructions"

    file_name = Column(String(100), nullable=False)
    raw_content = Column(Text, nullable=False)
    parsed_rules = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)

    # Relationships
    business = relationship("Business", back_populates="instructions")


class BrainInstruction(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Specific operational rule, custom knowledge, or behavioral instruction learned by the Robot Brain."""
    __tablename__ = "brain_instructions"

    instruction = Column(Text, nullable=False)
    category = Column(String(50), nullable=False, default="RULE")  # RULE, DISCOUNT, TIMING, FAQ, BEHAVIOR, POLICY
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String(50), nullable=False, default="WEB_PANEL")  # WEB_PANEL, CHAT_TEACH, VOICE, SEED
