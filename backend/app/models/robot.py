"""Robot device model representing the physical ESP32 hardware."""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.database.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RobotDevice(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Physical robot device identity, telemetry, and live state."""
    __tablename__ = "robots"

    robot_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False, default="Business AI Robot")
    shared_secret_hash = Column(String(255), nullable=True)
    firmware_version = Column(String(20), nullable=False, default="0.1.0")
    is_online = Column(Boolean, nullable=False, default=False)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    wifi_rssi = Column(Integer, nullable=True)
    relays_state = Column(JSON, nullable=False, default=lambda: [0, 0, 0, 0])
    peripherals_status = Column(JSON, nullable=False, default=lambda: {})

    # Relationships
    business = relationship("Business", back_populates="robots")
    commands = relationship("RobotCommand", back_populates="robot", cascade="all, delete-orphan")
