"""Comprehensive integration and unit tests for all 16 database models."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    ActorType,
    AIActivity,
    AuditLog,
    Base,
    Bill,
    BillItem,
    BillSource,
    Business,
    BusinessInstruction,
    CommandStatus,
    Customer,
    InventoryTransaction,
    Notification,
    NotificationCategory,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
    Reminder,
    ReminderSource,
    RobotCommand,
    RobotDevice,
    Supplier,
    TransactionType,
    User,
    UserRole,
)


@pytest.fixture
def db_session() -> Session:
    """Creates a fresh, isolated in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_create_business_and_users(db_session: Session):
    """Test creating a business tenant and attaching Owner and Staff users."""
    business = Business(
        name="Omkar General Store",
        business_type="Grocery",
        owner_name="Omkar Jadhav",
        phone="+91-9876543210",
        working_hours="8:00 AM - 9:00 PM",
    )
    db_session.add(business)
    db_session.commit()
    db_session.refresh(business)

    assert business.id is not None
    assert business.name == "Omkar General Store"

    # Add Owner
    owner = User(
        business_id=business.id,
        username="omkar_owner",
        email="omkar@example.com",
        hashed_password="secure_hashed_password",
        full_name="Omkar Jadhav",
        role=UserRole.OWNER,
    )
    # Add Staff
    staff = User(
        business_id=business.id,
        username="rahul_staff",
        email="rahul@example.com",
        hashed_password="secure_hashed_password_staff",
        full_name="Rahul Kumar",
        role=UserRole.STAFF,
    )
    db_session.add_all([owner, staff])
    db_session.commit()

    db_session.refresh(business)
    assert len(business.users) == 2
    roles = {u.role for u in business.users}
    assert UserRole.OWNER in roles
    assert UserRole.STAFF in roles


def test_robot_device_and_commands(db_session: Session):
    """Test registering an ESP32 robot and dispatching lifecycle commands."""
    biz = Business(name="Tech Store", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    robot = RobotDevice(
        business_id=biz.id,
        robot_id="ROBOT-001",
        name="Counter Robot",
        firmware_version="0.1.0",
        is_online=True,
        relays_state=[0, 0, 0, 0],
    )
    db_session.add(robot)
    db_session.commit()

    assert robot.id is not None
    assert robot.robot_id == "ROBOT-001"

    # Dispatch Command
    cmd = RobotCommand(
        business_id=biz.id,
        robot_id=robot.id,
        command_id="cmd_relay_1_on",
        action="relay",
        payload={"relay": 1, "state": "on"},
        status=CommandStatus.PENDING,
    )
    db_session.add(cmd)
    db_session.commit()

    # Verify lifecycle transition PENDING -> SENT -> SUCCESS
    cmd.status = CommandStatus.SENT
    db_session.commit()
    assert cmd.status == CommandStatus.SENT

    cmd.status = CommandStatus.SUCCESS
    cmd.result_payload = {"relay_1": "on", "duration_ms": 15}
    db_session.commit()

    db_session.refresh(robot)
    assert len(robot.commands) == 1
    assert robot.commands[0].status == CommandStatus.SUCCESS


def test_inventory_and_stock_transactions(db_session: Session):
    """Test product creation and stock audit transactions."""
    biz = Business(name="Mart", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    supplier = Supplier(
        business_id=biz.id,
        name="Agro Commodities Ltd",
        phone="+91-1122334455",
        email="agro@example.com",
    )
    db_session.add(supplier)
    db_session.commit()

    # Create Product
    product = Product(
        business_id=biz.id,
        supplier_id=supplier.id,
        barcode="8901234567890",
        name="Refined Sugar",
        unit="kg",
        purchase_price=Decimal("35.00"),
        selling_price=Decimal("42.00"),
        current_stock=Decimal("50.00"),
        minimum_stock=Decimal("20.00"),
    )
    db_session.add(product)
    db_session.commit()

    # Add Stock Transaction
    txn = InventoryTransaction(
        business_id=biz.id,
        product_id=product.id,
        transaction_type=TransactionType.STOCK_IN,
        quantity=Decimal("30.00"),
        stock_before=Decimal("50.00"),
        stock_after=Decimal("80.00"),
        notes="Supplier restock shipment #PO-902",
    )
    product.current_stock = Decimal("80.00")
    db_session.add(txn)
    db_session.commit()

    db_session.refresh(product)
    assert product.current_stock == Decimal("80.00")
    assert len(product.transactions) == 1
    assert product.transactions[0].transaction_type == TransactionType.STOCK_IN
    assert product.transactions[0].quantity == Decimal("30.00")


def test_billing_workflow_and_payments(db_session: Session):
    """Test customer creation, invoice generation with items, and payment reduction."""
    biz = Business(name="Grocery Hub", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    customer = Customer(
        business_id=biz.id,
        name="Rahul Verma",
        phone="+91-9898989898",
        outstanding_balance=Decimal("0.00"),
    )
    product = Product(
        business_id=biz.id,
        name="Basmati Rice",
        unit="kg",
        purchase_price=Decimal("80.00"),
        selling_price=Decimal("110.00"),
        current_stock=Decimal("100.00"),
    )
    db_session.add_all([customer, product])
    db_session.commit()

    # Create Bill
    bill = Bill(
        business_id=biz.id,
        customer_id=customer.id,
        bill_number="BILL-0001",
        subtotal=Decimal("220.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("220.00"),
        payment_status=PaymentStatus.PENDING,
        source=BillSource.ROBOT_VOICE,
    )
    db_session.add(bill)
    db_session.commit()

    # Add Bill Items (2 kg @ ₹110)
    bill_item = BillItem(
        bill_id=bill.id,
        product_id=product.id,
        quantity=Decimal("2.00"),
        unit_price=Decimal("110.00"),
        total_price=Decimal("220.00"),
    )
    customer.outstanding_balance += Decimal("220.00")
    db_session.add(bill_item)
    db_session.commit()

    assert customer.outstanding_balance == Decimal("220.00")

    # Record Payment (Customer pays ₹150 via UPI)
    payment = Payment(
        business_id=biz.id,
        customer_id=customer.id,
        bill_id=bill.id,
        amount=Decimal("150.00"),
        payment_method=PaymentMethod.UPI,
        notes="UPI payment from PhonePe",
    )
    customer.outstanding_balance -= Decimal("150.00")
    bill.payment_status = PaymentStatus.PARTIAL
    db_session.add(payment)
    db_session.commit()

    db_session.refresh(customer)
    db_session.refresh(bill)
    assert customer.outstanding_balance == Decimal("70.00")
    assert bill.payment_status == PaymentStatus.PARTIAL
    assert len(customer.bills) == 1
    assert len(customer.payments) == 1


def test_reminders_and_notifications(db_session: Session):
    """Test creating operational reminders and proactive manager alerts."""
    biz = Business(name="Daily Store", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    reminder = Reminder(
        business_id=biz.id,
        title="Call oil supplier for fresh batch",
        due_datetime=datetime.now(timezone.utc) + timedelta(days=1),
        source=ReminderSource.ROBOT_VOICE,
    )
    notification = Notification(
        business_id=biz.id,
        title="Low Stock Alert: Sugar",
        message="Sugar inventory is at 8 kg (below 20 kg minimum threshold).",
        category=NotificationCategory.LOW_STOCK,
    )
    db_session.add_all([reminder, notification])
    db_session.commit()

    db_session.refresh(biz)
    assert len(biz.reminders) == 1
    assert len(biz.notifications) == 1
    assert biz.notifications[0].category == NotificationCategory.LOW_STOCK


def test_business_instructions_and_ai_activity(db_session: Session):
    """Test custom instruction upload and conversational AI query logging."""
    biz = Business(name="Metro Retail", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    instructions = BusinessInstruction(
        business_id=biz.id,
        file_name="store_guidelines.txt",
        raw_content="Working hours 8 AM - 9 PM. Regular customers get 5% discount on rice.",
        parsed_rules={"regular_customer_discount": 0.05},
        is_active=True,
    )
    ai_log = AIActivity(
        business_id=biz.id,
        robot_id="ROBOT-001",
        user_query="How much sugar is left?",
        ai_response_text="You have 32 kilograms of sugar available.",
        structured_tool_name="get_product_stock",
        structured_tool_payload={"product": "sugar"},
        execution_status="SUCCESS",
        latency_ms=280,
    )
    db_session.add_all([instructions, ai_log])
    db_session.commit()

    db_session.refresh(biz)
    assert len(biz.instructions) == 1
    assert biz.instructions[0].parsed_rules["regular_customer_discount"] == 0.05


def test_audit_logs(db_session: Session):
    """Test immutable audit logging for security and compliance."""
    biz = Business(name="Safe Store", owner_name="Owner", phone="123")
    db_session.add(biz)
    db_session.commit()

    audit = AuditLog(
        business_id=biz.id,
        actor_type=ActorType.ROBOT,
        actor_id="ROBOT-001",
        action="RELAY_TOGGLE",
        entity_type="RELAY",
        entity_id="1",
        details={"state": "ON", "trigger": "voice_command"},
        ip_address="192.168.1.55",
    )
    db_session.add(audit)
    db_session.commit()

    db_session.refresh(biz)
    assert len(biz.audit_logs) == 1
    assert biz.audit_logs[0].actor_type == ActorType.ROBOT
    assert biz.audit_logs[0].action == "RELAY_TOGGLE"


def test_multi_tenant_isolation(db_session: Session):
    """Verify strict tenant isolation between two distinct businesses."""
    store_a = Business(name="Store A - Pune", owner_name="Owner A", phone="111")
    store_b = Business(name="Store B - Mumbai", owner_name="Owner B", phone="222")
    db_session.add_all([store_a, store_b])
    db_session.commit()

    prod_a = Product(business_id=store_a.id, name="Sugar Store A", current_stock=Decimal("100"))
    prod_b = Product(business_id=store_b.id, name="Sugar Store B", current_stock=Decimal("500"))
    db_session.add_all([prod_a, prod_b])
    db_session.commit()

    # Query strictly for Store A
    store_a_products = db_session.query(Product).filter(Product.business_id == store_a.id).all()
    assert len(store_a_products) == 1
    assert store_a_products[0].name == "Sugar Store A"

    # Query strictly for Store B
    store_b_products = db_session.query(Product).filter(Product.business_id == store_b.id).all()
    assert len(store_b_products) == 1
    assert store_b_products[0].name == "Sugar Store B"
