"""Pydantic schemas for Robot telemetry, heartbeat, commands, and voice interaction."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RobotPeripheralStatus(BaseModel):
    """Health status of connected hardware peripherals."""
    mic: str = Field(default="unknown", description="INMP441 status: ok, error, uninitialized, virtual")
    speaker: str = Field(default="unknown", description="MAX98357A status: ok, error, uninitialized, virtual")
    oled: str = Field(default="unknown", description="SSD1306 OLED status: ok, error, uninitialized, virtual")
    relays: str = Field(default="unknown", description="Relay module status: ok, error, uninitialized")


class RobotHeartbeatRequest(BaseModel):
    """Heartbeat payload sent periodically by the ESP32 robot."""
    robot_id: str = Field(..., description="Unique hardware identifier (e.g. ROBOT-001)")
    firmware_version: str = Field(default="0.1.0", description="Firmware version string")
    wifi_rssi: Optional[int] = Field(default=None, description="Wi-Fi signal strength in dBm")
    peripherals: Dict[str, str] = Field(
        default_factory=dict,
        description="Dictionary of peripheral health statuses"
    )
    relays_state: List[int] = Field(
        default_factory=lambda: [0, 0, 0, 0],
        description="Current state of relays 1-4 (0 for OFF, 1 for ON)"
    )
    uptime_seconds: Optional[int] = Field(default=None, description="ESP32 uptime in seconds")


class RobotHeartbeatResponse(BaseModel):
    """Response returned to the robot confirming heartbeat receipt."""
    acknowledged: bool = True
    robot_id: str
    server_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    pending_commands_count: int = 0
    message: str = "Heartbeat received"


class RobotStatusResponse(BaseModel):
    """Robot health and online status presented to the Mobile App & Dashboard."""
    robot_id: str
    is_online: bool
    last_heartbeat: Optional[datetime] = None
    firmware_version: Optional[str] = None
    wifi_rssi: Optional[int] = None
    relays_state: List[int] = Field(default_factory=lambda: [0, 0, 0, 0])
    peripherals: Dict[str, str] = Field(default_factory=dict)
    seconds_since_last_heartbeat: Optional[float] = None
    pending_commands_count: int = 0


class RobotCommandCreate(BaseModel):
    """Request payload to queue an action on a robot."""
    action: str = Field(..., description="Action name: set_relay, set_all_relays, blink_led, reboot, ping")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters, e.g. {'relay': 1, 'state': 'on'}"
    )
    priority: int = Field(default=1, description="Command priority (higher executed first)")


class RobotCommand(BaseModel):
    """Complete representation of a queued, dispatched, or executed robot command."""
    command_id: str
    robot_id: str
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1
    status: str = Field(default="pending", description="pending, dispatched, acknowledged, failed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dispatched_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None


class RobotCommandAck(BaseModel):
    """Acknowledgment payload sent by the ESP32 after executing a command."""
    status: str = Field(default="success", description="Execution result: success or error")
    message: Optional[str] = Field(default=None, description="Execution details or error reason")
    relays_state: Optional[List[int]] = Field(default=None, description="Current relay states after execution")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


class VoiceInteractRequest(BaseModel):
    """Voice or text interaction prompt for the Central Brain."""
    text: str = Field(..., description="User voice prompt or transcribed text")
    robot_id: str = Field(default="ROBOT-001", description="Target robot ID")
    conversation_id: Optional[str] = Field(default=None, description="Persistent conversation session ID")
    business_id: Optional[str] = Field(default=None, description="Business tenant ID")


class VoiceInteractResponse(BaseModel):
    """Result of AI intent reasoning, including speech response and executed hardware command."""
    response_text: str = Field(..., description="Speech response text to be spoken by robot/virtual speaker")
    action_type: str = Field(default="conversation", description="conversation, hardware_action, business_query, billing_action")
    conversation_id: str = Field(..., description="Conversation session ID for subsequent turns")
    immediate_ack: Optional[str] = Field(default=None, description="Acoustic/text pre-acknowledgment phrase")
    state: str = Field(default="IDLE", description="Current conversation state (IDLE, AWAITING_INPUT, AWAITING_CONFIRMATION, etc.)")
    business_data: Optional[Dict[str, Any]] = Field(default=None, description="Structured business data returned from PostgreSQL")
    latencies: Optional[Dict[str, float]] = Field(default=None, description="Stage latency breakdown in milliseconds")
    command_dispatched: Optional[RobotCommand] = None

