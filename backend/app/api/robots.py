"""Robot telemetry, registration, status, and command lifecycle endpoints."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid
from fastapi import APIRouter, HTTPException, Path, status

from app.config import get_settings
from app.schemas.robot import (
    RobotHeartbeatRequest,
    RobotHeartbeatResponse,
    RobotStatusResponse,
    RobotCommandCreate,
    RobotCommand,
    RobotCommandAck,
)

router = APIRouter()
settings = get_settings()

# In-memory registry for Phase 1 & 4 (transfers to PostgreSQL in Phase 2/Milestone)
_robot_registry: Dict[str, dict] = {}


def get_robot_record(robot_id: str) -> dict:
    """Retrieve or initialize an in-memory robot record."""
    if robot_id not in _robot_registry:
        _robot_registry[robot_id] = {
            "robot_id": robot_id,
            "last_heartbeat": None,
            "firmware_version": None,
            "wifi_rssi": None,
            "relays_state": [0, 0, 0, 0],
            "peripherals": {
                "mic": "virtual",
                "speaker": "virtual",
                "oled": "virtual",
                "relays": "ok",
            },
            "registered_at": datetime.now(timezone.utc),
            "pending_commands": [],
            "command_history": [],
        }
    return _robot_registry[robot_id]


@router.post(
    "/{robot_id}/heartbeat",
    response_model=RobotHeartbeatResponse,
    status_code=status.HTTP_200_OK,
    summary="Record robot heartbeat and telemetry",
)
async def post_robot_heartbeat(
    robot_id: str = Path(..., description="The unique robot ID"),
    heartbeat: RobotHeartbeatRequest = ...,
) -> RobotHeartbeatResponse:
    """Process incoming heartbeat from physical robot (ESP32)."""
    now = datetime.now(timezone.utc)
    record = get_robot_record(robot_id)

    record["last_heartbeat"] = now
    record["firmware_version"] = heartbeat.firmware_version
    record["wifi_rssi"] = heartbeat.wifi_rssi
    if heartbeat.peripherals:
        record["peripherals"].update(heartbeat.peripherals)
    record["relays_state"] = heartbeat.relays_state
    record["uptime_seconds"] = heartbeat.uptime_seconds

    # Count pending commands
    pending_count = len(
        [cmd for cmd in record.get("pending_commands", []) if cmd["status"] == "pending"]
    )

    return RobotHeartbeatResponse(
        acknowledged=True,
        robot_id=robot_id,
        server_timestamp=now,
        pending_commands_count=pending_count,
        message="Heartbeat recorded successfully",
    )


@router.get(
    "/{robot_id}/status",
    response_model=RobotStatusResponse,
    summary="Get current health and online status of a robot",
)
async def get_robot_status(
    robot_id: str = Path(..., description="The unique robot ID"),
) -> RobotStatusResponse:
    """Check if robot is currently online and retrieve last known state."""
    if robot_id not in _robot_registry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Robot '{robot_id}' has not registered or sent any heartbeat",
        )

    record = _robot_registry[robot_id]
    last_hb: Optional[datetime] = record["last_heartbeat"]
    now = datetime.now(timezone.utc)

    is_online = False
    seconds_since: Optional[float] = None

    if last_hb is not None:
        delta = (now - last_hb).total_seconds()
        seconds_since = round(delta, 2)
        is_online = delta <= settings.HEARTBEAT_TIMEOUT_SECONDS

    pending_count = len(
        [cmd for cmd in record.get("pending_commands", []) if cmd["status"] == "pending"]
    )

    return RobotStatusResponse(
        robot_id=robot_id,
        is_online=is_online,
        last_heartbeat=last_hb,
        firmware_version=record.get("firmware_version"),
        wifi_rssi=record.get("wifi_rssi"),
        relays_state=record.get("relays_state", [0, 0, 0, 0]),
        peripherals=record.get("peripherals", {}),
        seconds_since_last_heartbeat=seconds_since,
        pending_commands_count=pending_count,
    )


@router.get(
    "",
    response_model=List[RobotStatusResponse],
    summary="List all known robots and their statuses",
)
async def list_robots() -> List[RobotStatusResponse]:
    """List all registered robots."""
    now = datetime.now(timezone.utc)
    results: List[RobotStatusResponse] = []

    for robot_id, record in _robot_registry.items():
        last_hb = record["last_heartbeat"]
        is_online = False
        seconds_since = None
        if last_hb:
            delta = (now - last_hb).total_seconds()
            seconds_since = round(delta, 2)
            is_online = delta <= settings.HEARTBEAT_TIMEOUT_SECONDS

        pending_count = len(
            [cmd for cmd in record.get("pending_commands", []) if cmd["status"] == "pending"]
        )

        results.append(
            RobotStatusResponse(
                robot_id=robot_id,
                is_online=is_online,
                last_heartbeat=last_hb,
                firmware_version=record.get("firmware_version"),
                wifi_rssi=record.get("wifi_rssi"),
                relays_state=record.get("relays_state", [0, 0, 0, 0]),
                peripherals=record.get("peripherals", {}),
                seconds_since_last_heartbeat=seconds_since,
                pending_commands_count=pending_count,
            )
        )
    return results


# ==============================================================================
# Robot Command Lifecycle
# ==============================================================================


@router.post(
    "/{robot_id}/commands",
    response_model=RobotCommand,
    status_code=status.HTTP_201_CREATED,
    summary="Queue an action command for the robot",
)
async def create_robot_command(
    robot_id: str = Path(..., description="Target robot ID"),
    cmd_in: RobotCommandCreate = ...,
) -> RobotCommand:
    """Queue an action (e.g. set_relay, blink_led) for the physical robot to execute."""
    record = get_robot_record(robot_id)
    cmd_id = f"cmd_{uuid.uuid4().hex[:8]}"

    command_obj = {
        "command_id": cmd_id,
        "robot_id": robot_id,
        "action": cmd_in.action,
        "params": cmd_in.params,
        "priority": cmd_in.priority,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "dispatched_at": None,
        "acknowledged_at": None,
        "result": None,
    }

    record["pending_commands"].append(command_obj)
    return RobotCommand(**command_obj)


@router.get(
    "/{robot_id}/commands/pending",
    response_model=List[RobotCommand],
    summary="Get and mark pending commands for the physical robot",
)
async def get_pending_commands(
    robot_id: str = Path(..., description="Robot polling for commands"),
) -> List[RobotCommand]:
    """Called by the physical ESP32 to poll for pending action commands."""
    record = get_robot_record(robot_id)
    pending = [cmd for cmd in record["pending_commands"] if cmd["status"] == "pending"]

    now = datetime.now(timezone.utc)
    for cmd in pending:
        cmd["status"] = "dispatched"
        cmd["dispatched_at"] = now

    return [RobotCommand(**cmd) for cmd in pending]


@router.post(
    "/{robot_id}/commands/{command_id}/ack",
    response_model=RobotCommand,
    summary="Acknowledge completion of a command by the robot",
)
async def acknowledge_robot_command(
    robot_id: str = Path(..., description="The robot ID"),
    command_id: str = Path(..., description="The command ID being acknowledged"),
    ack: RobotCommandAck = ...,
) -> RobotCommand:
    """Called by the physical ESP32 to confirm command execution and update hardware state."""
    record = get_robot_record(robot_id)
    target_cmd = None

    for cmd in record["pending_commands"]:
        if cmd["command_id"] == command_id:
            target_cmd = cmd
            break

    if not target_cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Command '{command_id}' not found for robot '{robot_id}'",
        )

    now = datetime.now(timezone.utc)
    target_cmd["status"] = "acknowledged" if ack.status == "success" else "failed"
    target_cmd["acknowledged_at"] = now
    target_cmd["result"] = {
        "status": ack.status,
        "message": ack.message,
        "relays_state": ack.relays_state,
        "error": ack.error,
    }

    if ack.relays_state is not None:
        record["relays_state"] = ack.relays_state

    # Move from pending list to command history
    record["pending_commands"] = [
        c for c in record["pending_commands"] if c["command_id"] != command_id
    ]
    record["command_history"].append(target_cmd)

    return RobotCommand(**target_cmd)
