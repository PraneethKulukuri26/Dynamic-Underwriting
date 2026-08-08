"""
Behavioral Biometrics Router
Module 3: Trajectory ingestion, device fingerprinting, and bot detection.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.schemas.biometrics import (
    TrajectoryBatchRequest, TrajectoryBatchResponse,
    DeviceFingerprintRequest, DeviceFingerprintResponse,
    BiometricAnalysisResponse, BotDetectionResult,
    CAPIEventRequest, CAPIEventResponse,
)
from backend.models.biometrics import BiometricSession, TrajectoryPoint, DeviceFingerprint
from backend.services.trajectory_analyzer import trajectory_analyzer
from backend.services.device_fingerprint import device_fingerprint_service
from backend.services.event_deduplicator import event_deduplicator
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/biometrics", tags=["Behavioral Biometrics"])


@router.post("/trajectory", response_model=TrajectoryBatchResponse)
async def ingest_trajectory(req: TrajectoryBatchRequest, db: AsyncSession = Depends(get_db)):
    """Ingest a batch of mouse/touch trajectory points from the EvTrack SDK."""
    # Get or create session
    result = await db.execute(
        select(BiometricSession).where(BiometricSession.session_token == req.session_token)
    )
    session = result.scalar_one_or_none()

    if not session:
        session = BiometricSession(
            session_token=req.session_token,
            applicant_id=req.applicant_id,
            analysis_status="PENDING",
        )
        db.add(session)
        await db.flush()

    # Count existing points
    existing_count_result = await db.execute(
        select(TrajectoryPoint).where(TrajectoryPoint.session_id == session.id)
    )
    existing_points = list(existing_count_result.scalars())
    start_index = len(existing_points)

    # Store new trajectory points
    for i, point in enumerate(req.points):
        tp = TrajectoryPoint(
            session_id=session.id,
            x=point.x,
            y=point.y,
            timestamp_ms=point.timestamp_ms,
            event_type=point.event_type,
            sequence_index=start_index + i,
        )
        db.add(tp)

    await db.flush()

    return TrajectoryBatchResponse(
        session_token=req.session_token,
        points_received=len(req.points),
        total_points=start_index + len(req.points),
    )


@router.post("/fingerprint", response_model=DeviceFingerprintResponse)
async def submit_fingerprint(req: DeviceFingerprintRequest, db: AsyncSession = Depends(get_db)):
    """Submit device fingerprint from the client SDK."""
    # Generate composite hash
    fp_data = req.model_dump(exclude={"session_token"})
    composite_hash = device_fingerprint_service.generate_composite_hash(fp_data)

    # Check if this fingerprint exists
    result = await db.execute(
        select(DeviceFingerprint).where(DeviceFingerprint.composite_hash == composite_hash)
    )
    existing = result.scalar_one_or_none()

    # Validate consistency
    consistency = device_fingerprint_service.validate_consistency(fp_data)

    if existing:
        existing.times_seen += 1
        existing.last_seen_at = datetime.now(timezone.utc)
        existing.is_consistent = consistency["is_consistent"]
        existing.consistency_details = consistency
        fingerprint = existing
        is_known = True
    else:
        fingerprint = DeviceFingerprint(
            composite_hash=composite_hash,
            canvas_hash=req.canvas_hash,
            webgl_vendor=req.webgl_vendor,
            webgl_renderer=req.webgl_renderer,
            webgl_hash=req.webgl_hash,
            webrtc_local_ips=req.webrtc_local_ips,
            webrtc_media_devices=req.webrtc_media_devices,
            user_agent=req.user_agent,
            platform=req.platform,
            screen_resolution=req.screen_resolution,
            timezone_offset=req.timezone_offset,
            language=req.language,
            color_depth=req.color_depth,
            hardware_concurrency=req.hardware_concurrency,
            is_consistent=consistency["is_consistent"],
            consistency_details=consistency,
        )
        db.add(fingerprint)
        await db.flush()
        is_known = False

    # Link to session
    session_result = await db.execute(
        select(BiometricSession).where(BiometricSession.session_token == req.session_token)
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.device_fingerprint_id = fingerprint.id

    return DeviceFingerprintResponse(
        fingerprint_id=fingerprint.id,
        composite_hash=composite_hash,
        is_known_device=is_known,
        times_seen=fingerprint.times_seen,
        is_consistent=consistency["is_consistent"],
        consistency_details=consistency,
    )


@router.get("/analysis/{session_token}")
async def get_biometric_analysis(session_token: str, db: AsyncSession = Depends(get_db)):
    """Run and return bot detection analysis for a session."""
    result = await db.execute(
        select(BiometricSession).where(BiometricSession.session_token == session_token)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session not found")

    # Load trajectory points
    points_result = await db.execute(
        select(TrajectoryPoint)
        .where(TrajectoryPoint.session_id == session.id)
        .order_by(TrajectoryPoint.sequence_index)
    )
    points = list(points_result.scalars())

    if len(points) < 10:
        raise HTTPException(400, "Insufficient trajectory data (minimum 10 points)")

    # Convert to dicts for analyzer
    point_dicts = [
        {"x": p.x, "y": p.y, "timestamp_ms": p.timestamp_ms, "event_type": p.event_type}
        for p in points
    ]

    # Run analysis
    analysis = await trajectory_analyzer.analyze(point_dicts)

    # Update session with results
    session.bigru_bot_score = analysis["bigru_bot_score"]
    session.rf_fraud_score = analysis["rf_fraud_score"]
    session.combined_bot_probability = analysis["combined_bot_probability"]
    session.is_bot = analysis["is_bot"]
    session.confidence = analysis["confidence"]
    session.mean_velocity = analysis["mean_velocity"]
    session.max_velocity = analysis["max_velocity"]
    session.mean_acceleration = analysis["mean_acceleration"]
    session.jitter_score = analysis["jitter_score"]
    session.path_straightness = analysis["path_straightness"]
    session.pause_count = analysis["pause_count"]
    session.total_distance = analysis.get("total_distance")
    session.session_duration_ms = analysis.get("session_duration_ms")
    session.click_count = analysis.get("click_count", 0)
    session.scroll_count = analysis.get("scroll_count", 0)
    session.analysis_status = "COMPLETED"
    session.analyzed_at = datetime.now(timezone.utc)

    return {
        "session_id": str(session.id),
        "session_token": session_token,
        "bot_detection": analysis,
        "total_trajectory_points": len(points),
        "analysis_status": "COMPLETED",
    }


@router.post("/event", response_model=CAPIEventResponse)
async def ingest_capi_event(req: CAPIEventRequest):
    """CAPI event ingestion with deduplication."""
    is_duplicate, status = await event_deduplicator.check_and_record(
        req.event_id, req.event_name, req.session_token
    )

    return CAPIEventResponse(
        event_id=req.event_id,
        status=status,
        is_duplicate=is_duplicate,
    )
