"""Product, Supplier, and InventoryTransaction models."""

import enum
from sqlalchemy import Boolean, Column, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TransactionType(str, enum.Enum):
    """Inventory adjustment transaction types."""
    STOCK_IN = "STOCK_IN"
    STOCK_OUT = "STOCK_OUT"
    SALE = "SALE"
    RETURN = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"


class Supplier(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Supplier vendor entity."""
    __tablename__ = "suppliers"

    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)

    # Relationships
    products = relationship("Product", back_populates="supplier")


class Product(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Product and stock definition (Database is authoritative price source)."""
    __tablename__ = "products"

    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    barcode = Column(String(50), nullable=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    unit = Column(String(20), nullable=False, default="kg")
    purchase_price = Column(Numeric(10, 2), nullable=False, default=0.00)
    selling_price = Column(Numeric(10, 2), nullable=False, default=0.00)
    current_stock = Column(Numeric(10, 2), nullable=False, default=0.00)
    minimum_stock = Column(Numeric(10, 2), nullable=False, default=0.00)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    business = relationship("Business", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    transactions = relationship("InventoryTransaction", back_populates="product", cascade="all, delete-orphan")
    bill_items = relationship("BillItem", back_populates="product")


class InventoryTransaction(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Immutable audit trail for every inventory change."""
    __tablename__ = "inventory_transactions"

    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False)
    stock_before = Column(Numeric(10, 2), nullable=False)
    stock_after = Column(Numeric(10, 2), nullable=False)
    reference_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    product = relationship("Product", back_populates="transactions")
