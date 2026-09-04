"""Customer, Bill, BillItem, and Payment models."""

import enum
from sqlalchemy import Column, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PaymentStatus(str, enum.Enum):
    """Invoice payment lifecycle status."""
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class BillSource(str, enum.Enum):
    """Origin of bill creation."""
    ROBOT_VOICE = "ROBOT_VOICE"
    APP_MANUAL = "APP_MANUAL"


class PaymentMethod(str, enum.Enum):
    """Payment channels."""
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"
    CREDIT = "CREDIT"


class Customer(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Customer entity with running ledger and outstanding balance."""
    __tablename__ = "customers"

    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=False, index=True)
    email = Column(String(100), nullable=True)
    outstanding_balance = Column(Numeric(10, 2), nullable=False, default=0.00)
    credit_limit = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    business = relationship("Business", back_populates="customers")
    bills = relationship("Bill", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")


class Bill(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Invoice header record (Calculated authoritatively by backend)."""
    __tablename__ = "bills"

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    bill_number = Column(String(50), nullable=False, index=True)
    subtotal = Column(Numeric(10, 2), nullable=False, default=0.00)
    tax_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0.00)
    payment_status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    source = Column(Enum(BillSource), nullable=False, default=BillSource.ROBOT_VOICE)

    # Relationships
    business = relationship("Business", back_populates="bills")
    customer = relationship("Customer", back_populates="bills")
    items = relationship("BillItem", back_populates="bill", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="bill")


class BillItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual line item within an invoice."""
    __tablename__ = "bill_items"

    bill_id = Column(UUID(as_uuid=True), ForeignKey("bills.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)

    # Relationships
    bill = relationship("Bill", back_populates="items")
    product = relationship("Product", back_populates="bill_items")


class Payment(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Payment transaction that offsets outstanding balance."""
    __tablename__ = "payments"

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    bill_id = Column(UUID(as_uuid=True), ForeignKey("bills.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False, default=PaymentMethod.CASH)
    notes = Column(Text, nullable=True)

    # Relationships
    business = relationship("Business", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")
    bill = relationship("Bill", back_populates="payments")
