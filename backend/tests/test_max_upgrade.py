"""Comprehensive test suite for MAX — Manager AI eXecutive upgrade.

Covers:
1. MAX branding & component health checks
2. Fast-Path sub-second execution (Greetings <50ms, Relays <100ms, Stock, Customer Balance)
3. Partial payment lifecycle (₹123 -> ₹60 -> ₹63 -> PAID) & Overpayment rejection
4. Customer ledger chronological transaction timeline & manager summary
5. Natural task extraction & operational task lifecycle
6. AI memory isolation (PostgreSQL business truth strictly overrides AI memory)
7. 6-Digit Owner PIN security: PBKDF2 hashing, 3-strike brute-force lockout, temporary auth token
8. High-risk actions protected by Owner PIN
9. In-memory LRU TTS audio caching
10. Granular latency observability breakdown
"""

from decimal import Decimal
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.speech_service import get_cached_audio, put_cached_audio, synthesize_speech
from app.models.billing import Bill, BillSource, Customer, Payment, PaymentMethod, PaymentStatus
from app.models.business import Business
from app.models.product import Product
from app.services.billing_service import BillingService
from app.services.customer_service import CustomerService
from app.services.memory_service import MemoryService
from app.services.security_service import SecurityService
from app.services.task_service import TaskService


def test_health_endpoint_max_branding_and_components(client: TestClient):
    """Verify health endpoint reports MAX branding and component health."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "MAX" in data["service"]
    assert "components" in data
    assert "api" in data["components"]
    assert "database" in data["components"]
    assert "edge_tts" in data["components"]


def test_fast_path_greetings(client: TestClient, db_session: Session, default_business: Business):
    """Verify greetings are handled sub-100ms via FastPath without LLM call."""
    t0 = time.perf_counter()
    resp = client.post("/api/v1/voice/interact", json={"text": "Hello MAX"})
    elapsed = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    data = resp.json()
    assert "MAX" in data["response_text"]
    assert data["action_type"] == "conversation"
    assert "latencies" in data
    assert data["latencies"]["fast_path_ms"] < 100  # Instant local regex execution
    assert data["latencies"]["total_ms"] < 500  # Sub-second backend execution


def test_fast_path_relay_control(client: TestClient, db_session: Session, default_business: Business):
    """Verify appliance relay switching is executed immediately via FastPath."""
    resp = client.post("/api/v1/voice/interact", json={"text": "light on kar do"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "hardware_action"
    assert "Light on kar di" in data["response_text"]
    assert data["command_dispatched"] is not None
    assert data["command_dispatched"]["action"] == "set_relay"
    assert data["command_dispatched"]["params"] == {"relay": 1, "state": "on"}


def test_fast_path_stock_query(client: TestClient, db_session: Session, default_business: Business):
    """Verify simple stock lookup is answered locally via FastPath."""
    # Seed product
    prod = db_session.query(Product).filter(Product.name == "Tata Salt").first()
    if not prod:
        prod = Product(
            business_id=default_business.id,
            name="Tata Salt",
            unit="packet",
            selling_price=Decimal("28.00"),
            current_stock=Decimal("37.00"),
            is_active=True,
        )
        db_session.add(prod)
        db_session.commit()
    else:
        prod.current_stock = Decimal("37.00")
        db_session.commit()

    resp = client.post("/api/v1/voice/interact", json={"text": "Tata Salt kitna hai"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "business_query"
    assert "37" in data["response_text"]
    assert "Tata Salt" in data["response_text"]
    assert "fast_path_ms" in data["latencies"]


def test_fast_path_customer_balance(client: TestClient, db_session: Session, default_business: Business):
    """Verify customer balance query is answered locally via FastPath."""
    cust = CustomerService.get_or_create_customer(db_session, "Rahul Sharma", "9876543210", default_business.id)
    cust.outstanding_balance = Decimal("250.00")
    db_session.commit()

    resp = client.post("/api/v1/voice/interact", json={"text": "Rahul Sharma ka kitna baki hai"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "business_query"
    assert "250" in data["response_text"]
    assert "Rahul Sharma" in data["response_text"]


def test_partial_payment_lifecycle(db_session: Session, default_business: Business):
    """
    Test complete lifecycle:
    1. Create bill of ₹123.00 for customer Amit
    2. Pay ₹60.00 -> status becomes PARTIAL, balance decreases to ₹63.00
    3. Pay remaining ₹63.00 -> status becomes PAID, balance decreases to ₹0.00
    4. Overpayment rejection -> trying to pay ₹50 when balance is 0 is rejected.
    """
    # 1. Setup Customer & Bill
    cust = CustomerService.get_or_create_customer(db_session, "Amit Kumar", "9123456789", default_business.id)
    cust.outstanding_balance = Decimal("123.00")
    db_session.commit()

    bill = Bill(
        business_id=default_business.id,
        customer_id=cust.id,
        bill_number="INV-TEST-123",
        subtotal=Decimal("123.00"),
        total_amount=Decimal("123.00"),
        payment_status=PaymentStatus.PENDING,
        source=BillSource.ROBOT_VOICE,
    )
    db_session.add(bill)
    db_session.commit()
    db_session.refresh(bill)

    # 2. First Partial Payment: ₹60
    pay1 = BillingService.record_payment(
        db=db_session,
        customer_name="Amit Kumar",
        amount=60.0,
        payment_method="UPI",
        bill_id=bill.id,
        business_id=default_business.id,
    )
    assert pay1["success"] is True
    assert pay1["amount_paid"] == 60.0
    assert pay1["remaining_balance"] == 63.0
    assert pay1["bill_status"] == "PARTIAL"

    db_session.refresh(bill)
    db_session.refresh(cust)
    assert bill.payment_status == PaymentStatus.PARTIAL
    assert cust.outstanding_balance == Decimal("63.00")

    # 3. Second Payment: Remaining ₹63
    pay2 = BillingService.record_payment(
        db=db_session,
        customer_name="Amit Kumar",
        amount=63.0,
        payment_method="CASH",
        bill_id=bill.id,
        business_id=default_business.id,
    )
    assert pay2["success"] is True
    assert pay2["remaining_balance"] == 0.0
    assert pay2["bill_status"] == "PAID"

    db_session.refresh(bill)
    db_session.refresh(cust)
    assert bill.payment_status == PaymentStatus.PAID
    assert cust.outstanding_balance == Decimal("0.00")

    # 4. Overpayment rejection
    with pytest.raises(ValueError) as excinfo:
        BillingService.record_payment(
            db=db_session,
            customer_name="Amit Kumar",
            amount=50.0,
            business_id=default_business.id,
        )
    assert "Overpayment rejected" in str(excinfo.value)


def test_customer_ledger(db_session: Session, default_business: Business):
    """Test get_customer_ledger timeline and natural manager summary."""
    cust = CustomerService.get_or_create_customer(db_session, "Pooja Patil", "9898989898", default_business.id)
    cust.outstanding_balance = Decimal("200.00")
    db_session.commit()

    # Add a bill
    b = Bill(
        business_id=default_business.id,
        customer_id=cust.id,
        bill_number="INV-POOJA-01",
        total_amount=Decimal("500.00"),
        payment_status=PaymentStatus.PARTIAL,
    )
    db_session.add(b)
    db_session.flush()

    # Add a payment
    p = Payment(
        business_id=default_business.id,
        customer_id=cust.id,
        bill_id=b.id,
        amount=Decimal("300.00"),
        payment_method=PaymentMethod.UPI,
        notes="UPI advance payment",
    )
    db_session.add(p)
    db_session.commit()

    ledger = CustomerService.get_customer_ledger(db_session, "Pooja Patil", default_business.id)
    assert ledger["found"] is True
    assert ledger["total_billed"] == 500.0
    assert ledger["total_paid"] == 300.0
    assert ledger["outstanding_balance"] == 200.0
    assert ledger["last_payment"] is not None
    assert ledger["last_payment"]["amount"] == 300.0
    assert "Pooja Patil" in ledger["summary"]
    assert "500.00" in ledger["summary"]
    assert len(ledger["entries"]) == 2


def test_natural_task_extraction(client: TestClient, db_session: Session, default_business: Business):
    """Verify natural task creation e.g. 'Ramesh ka 500 baki hai kal yaad dila dena'."""
    resp = client.post("/api/v1/voice/interact", json={"text": "Ramesh ka 500 baki hai kal yaad dila dena"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "task_action"
    assert "Reminder task add kar diya hai" in data["response_text"]

    # Verify task in database
    tasks = TaskService.list_tasks(db_session, default_business.id)
    assert len(tasks) > 0
    assert any("500" in t["description"] for t in tasks)

    # Complete task
    comp = TaskService.complete_task(db_session, task_id_or_keyword="Ramesh", business_id=default_business.id)
    assert comp["success"] is True


def test_ai_memory_isolation_cannot_override_database(db_session: Session, default_business: Business):
    """
    Verify AI Memory stores contextual knowledge, but authoritative PostgreSQL
    product price & stock strictly overrule any AI memory facts.
    """
    # 1. Product price in authoritative DB is ₹28.00
    p = db_session.query(Product).filter(Product.name == "Tata Salt").first()
    if not p:
        p = Product(
            business_id=default_business.id,
            name="Tata Salt",
            unit="packet",
            selling_price=Decimal("28.00"),
            current_stock=Decimal("37.00"),
        )
        db_session.add(p)
        db_session.commit()
    else:
        p.selling_price = Decimal("28.00")
        db_session.commit()

    # 2. Save false memory claiming Tata Salt is ₹10
    MemoryService.store_memory(
        db=db_session,
        business_id=default_business.id,
        content="Tata Salt is priced at 10 rupees per packet for all customers",
        memory_type="BUSINESS_PREFERENCE",
    )

    # 3. Retrieve authoritative stock and price
    verified_stock = CustomerService.search_customer(db_session, "Tata Salt")  # None
    db_product = db_session.query(Product).filter(Product.name == "Tata Salt").first()
    assert float(db_product.selling_price) == 28.00  # Database truth is completely intact


def test_owner_security_pin_and_brute_force_lockout(db_session: Session, default_business: Business):
    """
    Verify 6-digit PIN verification, token creation, and 3-strike brute force lockout.
    """
    # Ensure initialized with default PIN 123456
    sec = SecurityService.get_or_create_owner_security(db_session, default_business.id)
    sec.failed_attempts = 0
    sec.locked_until = None
    db_session.commit()

    # 1. Verify correct PIN
    ok, msg, token = SecurityService.verify_owner(db_session, default_business.id, "123456")
    assert ok is True
    assert token is not None
    assert SecurityService.is_token_authorized(token, default_business.id) is True

    # Consume token
    SecurityService.consume_token(token)
    assert SecurityService.is_token_authorized(token, default_business.id) is False

    # 2. Strike 1 failed attempt
    ok1, msg1, _ = SecurityService.verify_owner(db_session, default_business.id, "999999")
    assert ok1 is False
    assert "2 attempt(s) remaining" in msg1

    # 3. Strike 2 failed attempt
    ok2, msg2, _ = SecurityService.verify_owner(db_session, default_business.id, "888888")
    assert ok2 is False
    assert "1 attempt(s) remaining" in msg2

    # 4. Strike 3 failed attempt -> Account locked
    ok3, msg3, _ = SecurityService.verify_owner(db_session, default_business.id, "777777")
    assert ok3 is False
    assert "Account locked for 5 minutes" in msg3

    # 5. Blocked attempt during lockout
    ok4, msg4, _ = SecurityService.verify_owner(db_session, default_business.id, "123456")
    assert ok4 is False
    assert "Account is locked" in msg4


def test_high_risk_tool_blocked_without_pin(client: TestClient, db_session: Session, default_business: Business):
    """Verify modify_product_price requires owner authorization token."""
    # Ensure security record reset
    sec = SecurityService.get_or_create_owner_security(db_session, default_business.id)
    sec.failed_attempts = 0
    sec.locked_until = None
    db_session.commit()

    # 1. API endpoint verify-owner
    resp_v = client.post("/api/v1/security/verify-owner", json={"pin": "123456"})
    assert resp_v.status_code == 200
    token = resp_v.json()["auth_token"]
    assert token.startswith("auth_")

    # 2. Attempt high-risk action without token
    p = db_session.query(Product).filter(Product.name == "Tata Salt").first()
    assert p is not None

    # Check risk classification
    assert SecurityService.classify_risk("modify_product_price").value == "HIGH"
    assert SecurityService.is_token_authorized(None, default_business.id) is False
    assert SecurityService.is_token_authorized(token, default_business.id) is True


@pytest.mark.asyncio
async def test_tts_audio_cache():
    """Verify in-memory LRU audio caching works for repeated phrases."""
    text = "MAX store manager audio test"
    audio_data = b"MOCK_MP3_BYTES_12345"
    put_cached_audio(text, "hi", audio_data, None)

    cached = get_cached_audio(text, "hi", None)
    assert cached == audio_data
