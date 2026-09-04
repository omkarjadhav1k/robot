"""User and RBAC role model."""

import enum
from sqlalchemy import Boolean, Column, Enum, String
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    """User authorization roles."""
    OWNER = "OWNER"
    STAFF = "STAFF"


class User(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """System user belonging to a business with role-based permissions."""
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.STAFF)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    business = relationship("Business", back_populates="users")
