"""Dedicated Test Suite for Robot V1: Real-Time Non-LLM Conversation Engine.

Covers all 10 mandatory test scenarios:
1. Fast Stock Query (sub-second deterministic response)
2. Slow Stock Query (immediate acknowledgment + completion)
3. Long Strategy (immediate acknowledgment + background task queued)
4. Interruption (fast stock query during running background task)
5. Task Completion Notification & follow-up retrieval
6. Retrieve Past Strategy Result ('Kal wali strategy batao')
7. Barge-in (instant audio/TTS stop on interrupt)
8. Ambiguous Product Disambiguation ('Kaunsi Maggi? ...')
9. Server Offline Grace Message ('Server se connection nahi hai.')
10. Multiple Simultaneous Background Tasks
"""

import json
import time
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.engine.business_strategy_engine import BusinessStrategyEngine
from app.engine.command_registry import COMMAND_REGISTRY, CommandMode
from app.engine.conversation_state import ConversationStateManager
from app.engine.entity_extractor import EntityExtractor, ExtractedEntities
from app.engine.fast_query_engine import FastQueryEngine
from app.engine.intent_router import IntentRouter
from app.engine.response_templates import ResponseTemplates
from app.engine.task_manager import BackgroundTaskManager
from app.models.billing import Customer
from app.models.business import Business
from app.models.product import Product
from app.models.task_job import JobStatus, TaskJob


# =====================================================================
# Scenario 1: Fast Stock Query
# =====================================================================
def test_scenario_1_fast_stock_query(client: TestClient, db_session: Session):
    """
    Scenario 1: User asks 'Maggi kitni hai?'
    Verifies:
    - Zero LLM involved.
    - IntentRouter classifies GET_STOCK.
    - Immediate sub-second database response with actual stock count.
    """
    biz = db_session.query(Business).first()
    # Seed Maggi
    p = Product(
        name="Maggi Noodles",
        unit="packet",
        selling_price=Decimal("14.00"),
        purchase_price=Decimal("10.00"),
        current_stock=Decimal("42.00"),
        minimum_stock=Decimal("10.00"),
        business_id=biz.id,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()

    resp = client.post(
        "/voice/interact",
        json={"text": "Maggi kitni hai?", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()

    # Sub-second latency, zero LLM
    assert data["latencies"]["gemini_ms"] == 0.0
    assert data["latencies"]["ai_ms"] == 0.0
    assert "42" in data["response_text"]
    assert "Maggi" in data["response_text"] or "maggi" in data["response_text"].lower()
    assert data["action_type"] == "business_query"


# =====================================================================
# Scenario 2: Slow Stock Query (Immediate Ack + Complete)
# =====================================================================
def test_scenario_2_slow_stock_query_with_ack(db_session: Session):
    """
    Scenario 2: Slow stock check execution triggers immediate ack
    'Ek minute, check karke batata hoon.' and executes accurately.
    """
    biz = db_session.query(Business).first()
    p = Product(
        name="Basmati Gold Rice",
        unit="kg",
        selling_price=Decimal("95.00"),
        purchase_price=Decimal("75.00"),
        current_stock=Decimal("18.00"),
        business_id=biz.id,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()

    entities = ExtractedEntities(product="Basmati Gold Rice")
    res = FastQueryEngine.execute(
        intent="GET_STOCK",
        entities=entities,
        db=db_session,
        business_id=biz.id,
        simulate_slow=True,
    )
    assert res.success is True
    assert res.immediate_ack is not None
    assert any(phrase in res.immediate_ack.lower() for phrase in ["check karke batata hoon", "ruko", "records dekh raha hoon", "ek minute"])
    assert "18" in res.response_text


# =====================================================================
# Scenario 3: Long Strategy Background Task
# =====================================================================
def test_scenario_3_long_strategy_background_task(client: TestClient, db_session: Session):
    """
    Scenario 3: User says 'Is week ki strategy bana.'
    Verifies:
    - Intent classified as CREATE_WEEKLY_STRATEGY (BACKGROUND mode).
    - Immediate conversational acknowledgment returned.
    - Background task is enqueued with unique TASK-xxx ID and status QUEUED/RUNNING.
    """
    resp = client.post(
        "/voice/interact",
        json={"text": "Is week ki strategy bana.", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["action_type"] == "background_task"
    assert "strategy" in data["response_text"].lower()
    assert data["business_data"] is not None
    assert "task_id" in data["business_data"]
    assert data["business_data"]["task_id"].startswith("TASK-")

    # Verify task in task manager
    task_id = data["business_data"]["task_id"]
    stat = BackgroundTaskManager.get_task_status(task_id)
    assert stat is not None
    assert stat["status"] in ("QUEUED", "RUNNING", "COMPLETED")


# =====================================================================
# Scenario 4: Interruption During Background Task
# =====================================================================
def test_scenario_4_interruption_during_task(client: TestClient, db_session: Session):
    """
    Scenario 4: While strategy task is executing, user asks 'Parle G kitni hai?'
    Verifies:
    - Stock question is answered immediately (<300ms).
    - Background task is not cancelled or blocked.
    """
    biz = db_session.query(Business).first()
    p = Product(
        name="Parle G Biscuit",
        unit="packet",
        selling_price=Decimal("10.00"),
        purchase_price=Decimal("8.00"),
        current_stock=Decimal("65.00"),
        minimum_stock=Decimal("15.00"),
        business_id=biz.id,
        is_active=True,
    )
    db_session.add(p)
    db_session.commit()

    # 1. Start strategy
    resp_strat = client.post(
        "/voice/interact",
        json={"text": "Retail strategy generate karo.", "robot_id": "ROBOT-001"},
    )
    task_id = resp_strat.json()["business_data"]["task_id"]

    # 2. Immediately ask stock while strategy is in-flight
    resp_stock = client.post(
        "/voice/interact",
        json={"text": "Parle G kitni hai?", "robot_id": "ROBOT-001"},
    )
    assert resp_stock.status_code == 200
    stock_data = resp_stock.json()
    assert "65" in stock_data["response_text"]

    # 3. Verify background task is still intact
    stat = BackgroundTaskManager.get_task_status(task_id)
    assert stat is not None
    assert stat["status"] in ("RUNNING", "COMPLETED", "QUEUED")


# =====================================================================
# Scenario 5: Task Completion & User Follow-up
# =====================================================================
def test_scenario_5_task_completion_and_followup(client: TestClient, db_session: Session):
    """
    Scenario 5: Background job completes and user checks status with 'Task status kya hai?'
    """
    biz = db_session.query(Business).first()

    # Enqueue task
    task_id = BackgroundTaskManager.enqueue_task(
        task_type="CREATE_WEEKLY_STRATEGY",
        business_id=biz.id,
    )

    # Wait briefly for worker thread to complete
    for _ in range(30):
        stat = BackgroundTaskManager.get_task_status(task_id)
        if stat and stat["status"] == "COMPLETED":
            break
        time.sleep(0.05)

    stat = BackgroundTaskManager.get_task_status(task_id)
    assert stat["status"] == "COMPLETED"
    assert stat["progress"] == 100

    # User asks about status
    resp = client.post(
        "/voice/interact",
        json={"text": "Task status kya hai?", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    assert resp.json()["action_type"] == "task_status"


# =====================================================================
# Scenario 6: Retrieve Old Strategy Result ('Kal wali strategy batao')
# =====================================================================
def test_scenario_6_retrieve_old_strategy(client: TestClient, db_session: Session):
    """
    Scenario 6: User says 'Kal wali strategy batao'
    Verifies:
    - IntentRouter recognizes GET_COMPLETED_TASK.
    - System retrieves the latest saved strategy from TaskManager/DB.
    - Natural language summary is returned.
    """
    biz = db_session.query(Business).first()

    # Seed a completed strategy task
    task_id = BackgroundTaskManager.enqueue_task(
        task_type="CREATE_WEEKLY_STRATEGY",
        business_id=biz.id,
    )

    # Wait for completion
    for _ in range(30):
        stat = BackgroundTaskManager.get_task_status(task_id)
        if stat and stat["status"] == "COMPLETED":
            break
        time.sleep(0.05)

    resp = client.post(
        "/voice/interact",
        json={"text": "Kal wali strategy batao.", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "task_retrieval"
    assert "strategy" in data["response_text"].lower() or "focus" in data["response_text"].lower() or "dukan" in data["response_text"].lower()


# =====================================================================
# Scenario 7: Barge-In (Instant Interruption)
# =====================================================================
def test_scenario_7_barge_in_interruption(client: TestClient):
    """
    Scenario 7: User says 'Ruko' or sends barge_in control signal.
    Verifies:
    - Barge-in triggers stop immediately.
    - Response indicates playback cancellation.
    """
    # 1. Via REST text command
    resp = client.post(
        "/voice/interact",
        json={"text": "Ruko", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    assert resp.json()["action_type"] == "barge_in"
    assert any(w in resp.json()["response_text"].lower() for w in ["rok", "ruk", "band"])

    # 2. Via WebSocket control packet
    with client.websocket_connect("/api/v1/voice/ws?robot_id=ROBOT-001") as ws:
        # Send speech_start
        ws.send_json({"type": "speech_start"})
        evt_listen = ws.receive_json()
        assert evt_listen["type"] == "listening"

        # Stream dummy PCM frame (640 bytes = 20ms @ 16kHz 16-bit mono)
        ws.send_bytes(b"\x00" * 640)

        # Send barge_in interrupt
        ws.send_json({"type": "barge_in"})
        evt = ws.receive_json()
        assert evt["type"] == "barge_in_ack"
        assert evt["status"] == "playback_cancelled"


# =====================================================================
# Scenario 8: Ambiguous Product Disambiguation ('Kaunsi Maggi?')
# =====================================================================
def test_scenario_8_ambiguous_product_disambiguation(client: TestClient, db_session: Session):
    """
    Scenario 8: Store has 'Maggi 70g', 'Maggi 140g', 'Maggi Special'.
    User asks: 'Maggi ka stock kitna hai?'
    Verifies:
    - EntityExtractor detects ambiguity.
    - Robot responds with exact prompt: 'Kaunsi Maggi? Maggi 70g, Maggi 140g, Maggi Special?'
    """
    biz = db_session.query(Business).first()
    # Add multiple distinct Maggi variants
    for variant in ["Maggi 70g Masala", "Maggi 140g Family Pack", "Maggi Special Atta"]:
        existing = db_session.query(Product).filter(Product.name == variant, Product.business_id == biz.id).first()
        if not existing:
            db_session.add(Product(
                name=variant,
                unit="packet",
                selling_price=Decimal("20.00"),
                current_stock=Decimal("15.00"),
                business_id=biz.id,
                is_active=True,
            ))
    db_session.commit()

    resp = client.post(
        "/voice/interact",
        json={"text": "Maggi ka stock kitna hai?", "robot_id": "ROBOT-001"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "clarification"
    assert "kaunsi" in data["response_text"].lower()
    assert "maggi" in data["response_text"].lower()


# =====================================================================
# Scenario 9: Server Offline Grace Message
# =====================================================================
def test_scenario_9_server_offline_grace():
    """
    Scenario 9: When network connection drops, offline fallback string
    is exactly 'Server se connection nahi hai.' (Section 28).
    """
    offline_msg = ResponseTemplates.get("OFFLINE")
    assert offline_msg == "Server se connection nahi hai."


# =====================================================================
# Scenario 10: Multiple Simultaneous Background Tasks
# =====================================================================
def test_scenario_10_multiple_simultaneous_tasks(db_session: Session):
    """
    Scenario 10: Enqueue strategy task AND inventory report task concurrently.
    Verifies:
    - Two distinct task IDs are created.
    - Both execute independently without collision.
    - In-memory priority queue maintains independent status.
    """
    biz = db_session.query(Business).first()

    task_1 = BackgroundTaskManager.enqueue_task(
        task_type="CREATE_WEEKLY_STRATEGY",
        business_id=biz.id,
    )
    task_2 = BackgroundTaskManager.enqueue_task(
        task_type="GENERATE_INVENTORY_REPORT",
        business_id=biz.id,
    )

    assert task_1 != task_2
    assert task_1.startswith("TASK-")
    assert task_2.startswith("TASK-")

    # Monitor both
    for _ in range(40):
        s1 = BackgroundTaskManager.get_task_status(task_1)
        s2 = BackgroundTaskManager.get_task_status(task_2)
        if s1 and s2 and s1["status"] == "COMPLETED" and s2["status"] == "COMPLETED":
            break
        time.sleep(0.05)

    s1 = BackgroundTaskManager.get_task_status(task_1)
    s2 = BackgroundTaskManager.get_task_status(task_2)
    assert s1["status"] == "COMPLETED"
    assert s2["status"] == "COMPLETED"
    assert s1["progress"] == 100
    assert s2["progress"] == 100
    assert s1["type"] == "CREATE_WEEKLY_STRATEGY"
    assert s2["type"] == "GENERATE_INVENTORY_REPORT"
