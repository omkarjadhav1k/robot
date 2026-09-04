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
