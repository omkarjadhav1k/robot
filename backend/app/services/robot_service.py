"""Authoritative Robot Service managing hardware persistence, heartbeat telemetry, and commands in PostgreSQL."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.models.robot import RobotDevice
from app.models.robot_command import CommandStatus, RobotCommand

logger = logging.getLogger(__name__)


class RobotService:
    """PostgreSQL-backed robot state, heartbeat, and hardware command queue management."""

    @staticmethod
    def get_or_create_robot(db: Session, robot_id: str, business_id: Optional[Any] = None) -> RobotDevice:
        """Fetch existing robot device or create database record on first connect."""
        robot = db.query(RobotDevice).filter(RobotDevice.robot_id == robot_id).first()
        if not robot:
            if not business_id:
                from app.models.business import Business
                default_biz = db.query(Business).first()
                if not default_biz:
                    default_biz = Business(name="Main Store", owner_name="Store Owner", business_type="Retail")
                    db.add(default_biz)
                    db.flush()
                business_id = default_biz.id

            robot = RobotDevice(
                robot_id=robot_id,
                name=f"Robot {robot_id}",
                firmware_version="0.1.0",
                is_online=True,
                last_heartbeat=datetime.now(timezone.utc),
                relays_state=[0, 0, 0, 0],
                peripherals_status={},
                business_id=business_id,
            )
            db.add(robot)
            db.commit()
            db.refresh(robot)
            logger.info("Registered new RobotDevice in database: %s", robot_id)
        return robot

    @staticmethod
    def record_heartbeat(
        db: Session,
        robot_id: str,
        firmware_version: Optional[str] = None,
        wifi_rssi: Optional[int] = None,
        relays_state: Optional[List[int]] = None,
        peripherals: Optional[Dict[str, str]] = None,
    ) -> RobotDevice:
        """Update robot online status, telemetry, and peripheral health in PostgreSQL."""
        robot = RobotService.get_or_create_robot(db, robot_id)
        robot.is_online = True
        robot.last_heartbeat = datetime.now(timezone.utc)
        if firmware_version:
            robot.firmware_version = firmware_version
        if wifi_rssi is not None:
            robot.wifi_rssi = wifi_rssi
        if relays_state is not None:
            robot.relays_state = relays_state
        if peripherals is not None:
            robot.peripherals_status = peripherals

        db.commit()
        db.refresh(robot)
        return robot

    @staticmethod
    def queue_command(
        db: Session,
        robot_id: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        priority: int = 1,
    ) -> RobotCommand:
        """Create a new command row in PostgreSQL with status PENDING."""
        robot = RobotService.get_or_create_robot(db, robot_id)
        cmd_id = f"cmd_{uuid.uuid4().hex[:12]}"
        cmd = RobotCommand(
            command_id=cmd_id,
            robot_id=robot.id,
            business_id=robot.business_id,
            action=action,
            payload=params or {},
            status=CommandStatus.PENDING,
        )
        db.add(cmd)
        db.commit()
        db.refresh(cmd)
        logger.info("Queued command %s (%s) for robot %s", cmd_id, action, robot_id)
        return cmd

    @staticmethod
    def pop_pending_command(db: Session, robot_id: str) -> Optional[RobotCommand]:
        """Fetch the oldest pending command for this robot and mark it as SENT."""
        robot = db.query(RobotDevice).filter(RobotDevice.robot_id == robot_id).first()
        if not robot:
            return None

        cmd = (
            db.query(RobotCommand)
            .filter(
                RobotCommand.robot_id == robot.id,
                RobotCommand.status == CommandStatus.PENDING,
            )
            .order_by(RobotCommand.created_at.asc())
            .first()
        )
        if cmd:
            cmd.status = CommandStatus.SENT
            db.commit()
            db.refresh(cmd)
        return cmd

    @staticmethod
    def acknowledge_command(
        db: Session,
        robot_id: str,
        command_id: str,
        status: str = "success",
        message: Optional[str] = None,
        relays_state: Optional[List[int]] = None,
        error: Optional[str] = None,
    ) -> Optional[RobotCommand]:
        """Record command completion or failure from ESP32."""
        cmd = db.query(RobotCommand).filter(RobotCommand.command_id == command_id).first()
        if not cmd:
            logger.warning("Command %s not found for ack", command_id)
            return None

        cmd.status = CommandStatus.SUCCESS if status == "success" else CommandStatus.FAILED
        cmd.result_payload = {
            "status": status,
            "message": message,
            "error": error,
        }
        if error:
            cmd.error_message = error

        # Update robot's relay state if reported
        if relays_state is not None:
            robot = db.query(RobotDevice).filter(RobotDevice.id == cmd.robot_id).first()
            if robot:
                robot.relays_state = relays_state

        db.commit()
        db.refresh(cmd)
        return cmd

    @staticmethod
    def get_robot_status(db: Session, robot_id: str) -> Dict[str, Any]:
        """Query live robot status and pending command count from database."""
        robot = db.query(RobotDevice).filter(RobotDevice.robot_id == robot_id).first()
        if not robot:
            return {
                "robot_id": robot_id,
                "is_online": False,
                "last_heartbeat": None,
                "firmware_version": None,
                "wifi_rssi": None,
                "relays_state": [0, 0, 0, 0],
                "peripherals": {},
                "seconds_since_last_heartbeat": None,
                "pending_commands_count": 0,
            }

        now = datetime.now(timezone.utc)
        last_hb = robot.last_heartbeat
        if last_hb and last_hb.tzinfo is None:
            last_hb = last_hb.replace(tzinfo=timezone.utc)
        secs_since = round((now - last_hb).total_seconds(), 2) if last_hb else None
        # Robot considered online if heartbeat seen within last 45 seconds
        is_online = (secs_since is not None and secs_since <= 45)

        pending_count = (
            db.query(RobotCommand)
            .filter(
                RobotCommand.robot_id == robot.id,
                RobotCommand.status == CommandStatus.PENDING,
            )
            .count()
        )

        return {
            "robot_id": robot.robot_id,
            "is_online": is_online,
            "last_heartbeat": robot.last_heartbeat,
            "firmware_version": robot.firmware_version,
            "wifi_rssi": robot.wifi_rssi,
            "relays_state": robot.relays_state or [0, 0, 0, 0],
            "peripherals": robot.peripherals_status or {},
            "seconds_since_last_heartbeat": secs_since,
            "pending_commands_count": pending_count,
        }
