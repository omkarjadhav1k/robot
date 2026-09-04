"""Pydantic schemas package."""

from app.schemas.robot import (
    RobotHeartbeatRequest,
    RobotHeartbeatResponse,
    RobotStatusResponse,
    RobotPeripheralStatus,
    RobotCommandCreate,
    RobotCommand,
    RobotCommandAck,
    VoiceInteractRequest,
    VoiceInteractResponse,
)

__all__ = [
    "RobotHeartbeatRequest",
    "RobotHeartbeatResponse",
    "RobotStatusResponse",
    "RobotPeripheralStatus",
    "RobotCommandCreate",
    "RobotCommand",
    "RobotCommandAck",
    "VoiceInteractRequest",
    "VoiceInteractResponse",
]
