"""Tests for Robot heartbeat, command lifecycle, and voice endpoints."""

from fastapi.testclient import TestClient


def test_robot_status_not_found(client: TestClient):
    """Querying status for an unregistered robot should return 404."""
    response = client.get("/robots/UNKNOWN-999/status")
    assert response.status_code == 404
    assert "not registered" in response.json()["detail"]


def test_robot_heartbeat_and_status(client: TestClient):
    """Posting a heartbeat should register the robot and report it online."""
    robot_id = "ROBOT-001"
    payload = {
        "robot_id": robot_id,
        "firmware_version": "0.1.0",
        "wifi_rssi": -65,
        "peripherals": {
            "mic": "virtual",
            "speaker": "virtual",
            "oled": "virtual",
            "relays": "ok",
        },
        "relays_state": [1, 0, 0, 0],
        "uptime_seconds": 120,
    }

    # 1. Post heartbeat
    hb_response = client.post(f"/robots/{robot_id}/heartbeat", json=payload)
    assert hb_response.status_code == 200
    hb_data = hb_response.json()
    assert hb_data["acknowledged"] is True
    assert hb_data["robot_id"] == robot_id
    assert hb_data["pending_commands_count"] == 0

    # 2. Query robot status
    status_response = client.get(f"/robots/{robot_id}/status")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["robot_id"] == robot_id
    assert status_data["is_online"] is True
    assert status_data["firmware_version"] == "0.1.0"
    assert status_data["wifi_rssi"] == -65
    assert status_data["relays_state"] == [1, 0, 0, 0]
    assert status_data["peripherals"]["mic"] == "virtual"
    assert status_data["seconds_since_last_heartbeat"] is not None
    assert status_data["seconds_since_last_heartbeat"] < 5.0


def test_robot_command_lifecycle(client: TestClient):
    """Verify full command lifecycle: create -> poll -> execute -> ack."""
    robot_id = "ROBOT-CMD-TEST"

    # 1. Register robot via heartbeat
    client.post(
        f"/robots/{robot_id}/heartbeat",
        json={"robot_id": robot_id, "firmware_version": "0.1.0"},
    )

    # 2. Backend / user queues a command
    create_resp = client.post(
        f"/robots/{robot_id}/commands",
        json={"action": "set_relay", "params": {"relay": 1, "state": "on"}},
    )
    assert create_resp.status_code == 201
    cmd_data = create_resp.json()
    cmd_id = cmd_data["command_id"]
    assert cmd_data["action"] == "set_relay"
    assert cmd_data["status"] == "pending"

    # 3. Physical ESP32 polls for pending commands
    poll_resp = client.get(f"/robots/{robot_id}/commands/pending")
    assert poll_resp.status_code == 200
    pending_cmds = poll_resp.json()
    assert len(pending_cmds) == 1
    assert pending_cmds[0]["command_id"] == cmd_id
    assert pending_cmds[0]["status"] == "dispatched"

    # 4. Physical ESP32 completes execution and sends ACK
    ack_resp = client.post(
        f"/robots/{robot_id}/commands/{cmd_id}/ack",
        json={
            "status": "success",
            "message": "Relay 1 turned ON",
            "relays_state": [1, 0, 0, 0],
        },
    )
    assert ack_resp.status_code == 200
    ack_data = ack_resp.json()
    assert ack_data["status"] == "acknowledged"

    # 5. Robot status reflects the updated relay states
    status_resp = client.get(f"/robots/{robot_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["relays_state"] == [1, 0, 0, 0]


def test_voice_hardware_command(client: TestClient):
    """Verify voice prompt triggering hardware action."""
    robot_id = "ROBOT-001"
    client.post(
        f"/robots/{robot_id}/heartbeat",
        json={"robot_id": robot_id, "firmware_version": "0.1.0"},
    )

    response = client.post(
        "/voice/interact",
        json={"text": "Robot, please turn on relay 2", "robot_id": robot_id},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action_type"] == "hardware_action"
    assert "Relay 2 has been switched on" in data["response_text"]
    assert data["command_dispatched"] is not None
    assert data["command_dispatched"]["action"] == "set_relay"
    assert data["command_dispatched"]["params"] == {"relay": 2, "state": "on"}
