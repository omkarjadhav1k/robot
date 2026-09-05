"""Database models package aggregating all declarative entity models."""

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.audit import ActorType, AuditLog
from app.models.billing import (
    Bill,
    BillItem,
    BillSource,
    Customer,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.models.business import Business
from app.models.conversation import (
    ConversationMessage,
    ConversationSession,
    ConversationState,
)
from app.models.instruction import BusinessInstruction
from app.models.product import (
    InventoryTransaction,
    Product,
    Supplier,
    TransactionType,
)
from app.models.reminder import (
    Notification,
    NotificationCategory,
    Reminder,
    ReminderSource,
)
from app.models.robot import RobotDevice
from app.models.robot_command import AIActivity, CommandStatus, RobotCommand
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "TenantMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "Business",
    "User",
    "UserRole",
    "RobotDevice",
    "Supplier",
    "Product",
    "InventoryTransaction",
    "TransactionType",
    "Customer",
    "Bill",
    "BillItem",
    "Payment",
    "PaymentStatus",
    "BillSource",
    "PaymentMethod",
    "Reminder",
    "Notification",
    "ReminderSource",
    "NotificationCategory",
    "BusinessInstruction",
    "RobotCommand",
    "AIActivity",
    "CommandStatus",
    "AuditLog",
    "ActorType",
    "ConversationSession",
    "ConversationMessage",
    "ConversationState",
]
