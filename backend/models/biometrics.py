"""
Behavioral Biometrics ORM Models
Stores mouse trajectory data, device fingerprints, and bot detection results.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class BiometricSession(Base):
    """
    A behavioral biometrics session capturing user interactions.
    Each page visit / form interaction creates one session.
    """
    __tablename__ = "biometric_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=True, index=True)
    session_token = Column(String(128), unique=True, nullable=False, index=True)

    # Bot detection results (dual-model)
    bigru_bot_score = Column(Float, nullable=True)          # 0.0 (human) - 1.0 (bot)
    rf_fraud_score = Column(Float, nullable=True)           # 0.0 (legit) - 1.0 (fraud)
    combined_bot_probability = Column(Float, nullable=True) # Weighted ensemble
    is_bot = Column(Boolean, nullable=True)
    confidence = Column(Float, nullable=True)

    # Session-level kinetic features (aggregated from trajectory points)
    mean_velocity = Column(Float, nullable=True)
    max_velocity = Column(Float, nullable=True)
    mean_acceleration = Column(Float, nullable=True)
    jitter_score = Column(Float, nullable=True)
    path_straightness = Column(Float, nullable=True)
    pause_count = Column(Integer, nullable=True)
    total_distance = Column(Float, nullable=True)
    session_duration_ms = Column(Integer, nullable=True)
    click_count = Column(Integer, default=0)
    scroll_count = Column(Integer, default=0)

    # Device fingerprint reference
    device_fingerprint_id = Column(UUID(as_uuid=True), ForeignKey("device_fingerprints.id"), nullable=True)

    analysis_status = Column(String(32), default="PENDING")  # PENDING, ANALYZING, COMPLETED
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    analyzed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    applicant = relationship("Applicant", back_populates="biometric_sessions")
    trajectory_points = relationship("TrajectoryPoint", back_populates="session", cascade="all, delete-orphan")
    device_fingerprint = relationship("DeviceFingerprint", back_populates="sessions")

    def __repr__(self):
        return f"<BiometricSession(id={self.id}, bot_score={self.combined_bot_probability})>"


class TrajectoryPoint(Base):
    """
    Individual mouse/touch coordinate captured by EvTrack polling.
    High-frequency (150ms interval) raw trajectory data.
    """
    __tablename__ = "trajectory_points"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("biometric_sessions.id"), nullable=False, index=True)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    timestamp_ms = Column(Integer, nullable=False)  # Milliseconds since session start
    event_type = Column(String(16), nullable=False)  # move, click, scroll, touch
    sequence_index = Column(Integer, nullable=False)  # Order in trajectory

    # Derived kinematic features (computed server-side)
    velocity = Column(Float, nullable=True)
    acceleration = Column(Float, nullable=True)
    jerk = Column(Float, nullable=True)
    curvature = Column(Float, nullable=True)

    # Relationships
    session = relationship("BiometricSession", back_populates="trajectory_points")

    def __repr__(self):
        return f"<TrajectoryPoint(x={self.x}, y={self.y}, t={self.timestamp_ms})>"


class DeviceFingerprint(Base):
    """
    Browser device fingerprint combining Canvas, WebGL, and WebRTC signals.
    """
    __tablename__ = "device_fingerprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    composite_hash = Column(String(64), unique=True, nullable=False, index=True)

    # Canvas fingerprint
    canvas_hash = Column(String(64), nullable=True)

    # WebGL fingerprint
    webgl_vendor = Column(String(128), nullable=True)
    webgl_renderer = Column(String(256), nullable=True)
    webgl_hash = Column(String(64), nullable=True)

    # WebRTC data
    webrtc_local_ips = Column(JSON, nullable=True)
    webrtc_media_devices = Column(JSON, nullable=True)

    # Browser metadata
    user_agent = Column(Text, nullable=True)
    platform = Column(String(64), nullable=True)
    screen_resolution = Column(String(32), nullable=True)
    timezone_offset = Column(Integer, nullable=True)
    language = Column(String(16), nullable=True)
    color_depth = Column(Integer, nullable=True)
    hardware_concurrency = Column(Integer, nullable=True)

    # Consistency checks
    is_consistent = Column(Boolean, nullable=True)  # UA matches reported GPU/OS
    consistency_details = Column(JSON, nullable=True)

    first_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    times_seen = Column(Integer, default=1)

    # Relationships
    sessions = relationship("BiometricSession", back_populates="device_fingerprint")

    def __repr__(self):
        return f"<DeviceFingerprint(hash={self.composite_hash[:16]}...)>"
