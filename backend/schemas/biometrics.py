"""
Behavioral Biometrics Schemas
Request/Response models for trajectory ingestion, fingerprinting, and bot detection.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# --- Trajectory Ingestion ---

class TrajectoryPointInput(BaseModel):
    """Single coordinate from EvTrack polling."""
    x: float
    y: float
    timestamp_ms: int = Field(..., description="Milliseconds since session start")
    event_type: str = Field(default="move", description="move, click, scroll, touch")


class TrajectoryBatchRequest(BaseModel):
    """Batch of trajectory points from client SDK."""
    session_token: str = Field(..., min_length=1)
    applicant_id: Optional[UUID] = None
    points: List[TrajectoryPointInput] = Field(..., min_length=1)


class TrajectoryBatchResponse(BaseModel):
    """Response after ingesting trajectory batch."""
    session_token: str
    points_received: int
    total_points: int
    status: str = "RECEIVED"


# --- Device Fingerprint ---

class DeviceFingerprintRequest(BaseModel):
    """Device fingerprint payload from client SDK."""
    session_token: str

    # Canvas
    canvas_hash: Optional[str] = None

    # WebGL
    webgl_vendor: Optional[str] = None
    webgl_renderer: Optional[str] = None
    webgl_hash: Optional[str] = None

    # WebRTC
    webrtc_local_ips: Optional[List[str]] = None
    webrtc_media_devices: Optional[List[dict]] = None

    # Browser metadata
    user_agent: Optional[str] = None
    platform: Optional[str] = None
    screen_resolution: Optional[str] = None
    timezone_offset: Optional[int] = None
    language: Optional[str] = None
    color_depth: Optional[int] = None
    hardware_concurrency: Optional[int] = None


class DeviceFingerprintResponse(BaseModel):
    """Fingerprint analysis response."""
    fingerprint_id: UUID
    composite_hash: str
    is_known_device: bool
    times_seen: int
    is_consistent: bool
    consistency_details: Optional[dict] = None


# --- Bot Detection Results ---

class BotDetectionResult(BaseModel):
    """Combined bot detection analysis."""
    session_token: str
    bigru_bot_score: float = Field(..., ge=0.0, le=1.0)
    rf_fraud_score: float = Field(..., ge=0.0, le=1.0)
    combined_bot_probability: float = Field(..., ge=0.0, le=1.0)
    is_bot: bool
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Kinetic features summary
    mean_velocity: Optional[float] = None
    max_velocity: Optional[float] = None
    jitter_score: Optional[float] = None
    path_straightness: Optional[float] = None

    analysis_status: str


class BiometricAnalysisResponse(BaseModel):
    """Full biometric analysis for a session."""
    session_id: UUID
    session_token: str
    bot_detection: BotDetectionResult
    device_fingerprint: Optional[DeviceFingerprintResponse] = None
    total_trajectory_points: int
    session_duration_ms: Optional[int]
    analyzed_at: Optional[datetime]


# --- CAPI Event ---

class CAPIEventRequest(BaseModel):
    """Server-side Conversion API event."""
    event_id: str = Field(..., description="Unique event ID for deduplication")
    event_name: str
    session_token: str
    timestamp: int
    payload: Optional[dict] = None


class CAPIEventResponse(BaseModel):
    """CAPI event acknowledgment."""
    event_id: str
    status: str  # ACCEPTED, DEDUPLICATED
    is_duplicate: bool
