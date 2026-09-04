"""Business root tenant model."""

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Business(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Business entity representing the top-level tenant."""
    __tablename__ = "businesses"

    name = Column(String(100), nullable=False, index=True)
    business_type = Column(String(50), nullable=False, default="General Store")
    owner_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=False, default="INR")
    working_hours = Column(String(100), nullable=False, default="8:00 AM - 9:00 PM")

    # Relationships
    users = relationship("User", back_populates="business", cascade="all, delete-orphan")
    robots = relationship("RobotDevice", back_populates="business", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="business", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="business", cascade="all, delete-orphan")
    bills = relationship("Bill", back_populates="business", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="business", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="business", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="business", cascade="all, delete-orphan")
    instructions = relationship("BusinessInstruction", back_populates="business", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="business", cascade="all, delete-orphan")
