"""Robot telemetry, registration, status, and command lifecycle endpoints backed by PostgreSQL."""

from datetime import datetime, timezone
import logging
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import get_db
from app.models.robot import RobotDevice
from app.models.robot_command import CommandStatus, RobotCommand as DBRobotCommand
from app.schemas.robot import (
    RobotCommand,
    RobotCommandAck,
    RobotCommandCreate,
    RobotHeartbeatRequest,
    RobotHeartbeatResponse,
    RobotStatusResponse,
)
from app.services.robot_service import RobotService

logger = logging.getLogger("business_ai_robot.robots_api")
router = APIRouter()
settings = get_settings()


def _to_schema_command(cmd: DBRobotCommand, robot_str_id: str) -> RobotCommand:
    """Convert database RobotCommand entity to API response schema."""
    status_map = {
        CommandStatus.PENDING: "pending",
        CommandStatus.VALIDATED: "pending",
        CommandStatus.SENT: "dispatched",
        CommandStatus.RECEIVED: "dispatched",
        CommandStatus.EXECUTING: "dispatched",
        CommandStatus.SUCCESS: "acknowledged",
        CommandStatus.FAILED: "failed",
    }
    return RobotCommand(
        command_id=cmd.command_id,
        robot_id=robot_str_id,
        action=cmd.action,
        params=cmd.payload or {},
        priority=1,
        status=status_map.get(cmd.status, "pending"),
        created_at=cmd.created_at,
        dispatched_at=cmd.updated_at if cmd.status in (CommandStatus.SENT, CommandStatus.RECEIVED, CommandStatus.EXECUTING) else None,
        acknowledged_at=cmd.updated_at if cmd.status in (CommandStatus.SUCCESS, CommandStatus.FAILED) else None,
        result=cmd.result_payload,
    )


@router.post(
    "/{robot_id}/heartbeat",
    response_model=RobotHeartbeatResponse,
    status_code=status.HTTP_200_OK,
    summary="Record robot heartbeat and telemetry",
)
async def post_robot_heartbeat(
    robot_id: str = Path(..., description="The unique robot ID"),
    heartbeat: RobotHeartbeatRequest = ...,
    db: Session = Depends(get_db),
) -> RobotHeartbeatResponse:
    """Process incoming heartbeat from physical robot (ESP32) and persist in PostgreSQL."""
    now = datetime.now(timezone.utc)
    robot = RobotService.record_heartbeat(
        db=db,
        robot_id=robot_id,
        firmware_version=heartbeat.firmware_version,
        wifi_rssi=heartbeat.wifi_rssi,
        relays_state=heartbeat.relays_state,
        peripherals=heartbeat.peripherals,
    )

    pending_count = (
        db.query(DBRobotCommand)
        .filter(
            DBRobotCommand.robot_id == robot.id,
            DBRobotCommand.status == CommandStatus.PENDING,
        )
        .count()
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
    db: Session = Depends(get_db),
) -> RobotStatusResponse:
    """Check if robot is currently online and retrieve authoritative state from PostgreSQL."""
    robot = db.query(RobotDevice).filter(RobotDevice.robot_id == robot_id).first()
    if not robot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Robot '{robot_id}' has not registered or sent any heartbeat",
        )

    st = RobotService.get_robot_status(db, robot_id)
    return RobotStatusResponse(
        robot_id=st["robot_id"],
        is_online=st["is_online"],
        last_heartbeat=st["last_heartbeat"],
        firmware_version=st["firmware_version"],
        wifi_rssi=st["wifi_rssi"],
        relays_state=st["relays_state"],
        peripherals=st["peripherals"],
        seconds_since_last_heartbeat=st["seconds_since_last_heartbeat"],
        pending_commands_count=st["pending_commands_count"],
    )


@router.get(
    "",
    response_model=List[RobotStatusResponse],
    summary="List all known robots and their statuses",
)
async def list_robots(db: Session = Depends(get_db)) -> List[RobotStatusResponse]:
    """List all registered robots in PostgreSQL."""
    robots = db.query(RobotDevice).all()
    results: List[RobotStatusResponse] = []
    for r in robots:
        st = RobotService.get_robot_status(db, r.robot_id)
        results.append(
            RobotStatusResponse(
                robot_id=st["robot_id"],
                is_online=st["is_online"],
                last_heartbeat=st["last_heartbeat"],
                firmware_version=st["firmware_version"],
                wifi_rssi=st["wifi_rssi"],
                relays_state=st["relays_state"],
                peripherals=st["peripherals"],
                seconds_since_last_heartbeat=st["seconds_since_last_heartbeat"],
                pending_commands_count=st["pending_commands_count"],
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
    db: Session = Depends(get_db),
) -> RobotCommand:
    """Queue an action (e.g. set_relay, blink_led) for the physical robot in PostgreSQL."""
    cmd = RobotService.queue_command(
        db=db,
        robot_id=robot_id,
        action=cmd_in.action,
        params=cmd_in.params,
        priority=cmd_in.priority,
    )
    return _to_schema_command(cmd, robot_id)


@router.get(
    "/{robot_id}/commands/pending",
    response_model=List[RobotCommand],
    summary="Get and mark pending commands for the physical robot",
)
async def get_pending_commands(
    robot_id: str = Path(..., description="Robot polling for commands"),
    db: Session = Depends(get_db),
) -> List[RobotCommand]:
    """Called by the physical ESP32 to poll for pending action commands."""
    cmd = RobotService.pop_pending_command(db, robot_id)
    if not cmd:
        return []
    return [_to_schema_command(cmd, robot_id)]


@router.post(
    "/{robot_id}/commands/{command_id}/ack",
    response_model=RobotCommand,
    summary="Acknowledge completion of a command by the robot",
)
async def acknowledge_robot_command(
    robot_id: str = Path(..., description="The robot ID"),
    command_id: str = Path(..., description="The command ID being acknowledged"),
    ack: RobotCommandAck = ...,
    db: Session = Depends(get_db),
) -> RobotCommand:
    """Called by the physical ESP32 to confirm command execution and update PostgreSQL state."""
    cmd = RobotService.acknowledge_command(
        db=db,
        robot_id=robot_id,
        command_id=command_id,
        status=ack.status,
        message=ack.message,
        relays_state=ack.relays_state,
        error=ack.error,
    )
    if not cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Command '{command_id}' not found",
        )
    return _to_schema_command(cmd, robot_id)
