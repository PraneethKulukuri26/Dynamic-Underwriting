"""
OSINT Pipeline Router
Module 2: Username lookup, breach checking, identity verification, and correlation.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.schemas.osint import (
    OSINTScanRequest, OSINTReportResponse,
    UsernameSearchRequest, UsernameSearchResponse,
    BreachCheckRequest, BreachCheckResponse,
    IdentityVerifyRequest, IdentityVerifyResponse,
    TrustScoreBreakdown, PlatformMatchResponse, BreachRecordResponse,
)
from backend.models.osint import OSINTReport, PlatformMatch, BreachRecord
from backend.services.sherlock_runner import sherlock_runner
from backend.services.breach_checker import breach_checker
from backend.services.identity_verifier import identity_verifier
from backend.services.correlation_engine import correlation_engine
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/osint", tags=["OSINT Pipeline"])


@router.post("/scan")
async def initiate_osint_scan(
    req: OSINTScanRequest,
    db: AsyncSession = Depends(get_db),
):
    """Initiate a full OSINT scan for an applicant (Sherlock + HIBP + Gov ID)."""
    # Create report record
    report = OSINTReport(
        applicant_id=req.applicant_id,
        scan_status="RUNNING",
        scan_started_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()

    # Run correlation engine
    try:
        results = await correlation_engine.correlate(
            email=req.email,
            phone=req.phone,
            username=req.username,
            pan_number=req.pan_number,
            aadhaar_number=req.aadhaar_number,
            uan_number=req.uan_number,
        )

        # Update report with results
        report.trust_score = results["overall_trust_score"]
        report.network_depth_score = results["network_depth_score"]
        report.footprint_longevity_score = results["footprint_longevity_score"]
        report.professional_consistency_score = results["professional_consistency_score"]
        report.identity_verification_score = results["identity_verification_score"]
        report.total_platforms_found = len(results.get("platform_matches", []))
        report.total_breaches_found = results.get("breach_data", {}).get("total_breaches", 0)
        report.identity_verified = results.get("identity_data", {}).get("pan_verified", False) or \
                                   results.get("identity_data", {}).get("aadhaar_verified", False)
        report.risk_flags = results.get("risk_flags", [])
        report.scan_status = "COMPLETED"
        report.scan_completed_at = datetime.now(timezone.utc)

        # Store platform matches
        for pm in results.get("platform_matches", []):
            match = PlatformMatch(
                osint_report_id=report.id,
                platform_name=pm["platform_name"],
                profile_url=pm.get("profile_url"),
                username_queried=pm["username_queried"],
                found=pm["found"],
                response_time_ms=pm.get("response_time_ms"),
                category=pm.get("category"),
            )
            db.add(match)

        # Store breach records
        for br in results.get("breach_data", {}).get("breaches", []):
            breach = BreachRecord(
                osint_report_id=report.id,
                breach_name=br["breach_name"],
                breach_date=datetime.fromisoformat(br["breach_date"]) if br.get("breach_date") else None,
                pwn_count=br.get("pwn_count"),
                data_classes=br.get("data_classes"),
                is_verified=br.get("is_verified", False),
            )
            db.add(breach)

        # Set oldest breach date
        breach_dates = [
            datetime.fromisoformat(br["breach_date"])
            for br in results.get("breach_data", {}).get("breaches", [])
            if br.get("breach_date")
        ]
        if breach_dates:
            report.oldest_breach_date = min(breach_dates)

    except Exception as e:
        report.scan_status = "FAILED"
        report.risk_flags = [f"SCAN_ERROR: {str(e)}"]

    await db.flush()

    return {
        "report_id": str(report.id),
        "scan_status": report.scan_status,
        "trust_score": report.trust_score,
        "total_platforms_found": report.total_platforms_found,
        "total_breaches_found": report.total_breaches_found,
        "risk_flags": report.risk_flags,
    }


@router.get("/report/{applicant_id}")
async def get_osint_report(applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get the latest OSINT report for an applicant."""
    result = await db.execute(
        select(OSINTReport)
        .where(OSINTReport.applicant_id == applicant_id)
        .order_by(OSINTReport.created_at.desc())
        .limit(1)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "No OSINT report found for this applicant")

    # Load relationships
    matches_result = await db.execute(
        select(PlatformMatch).where(PlatformMatch.osint_report_id == report.id)
    )
    breaches_result = await db.execute(
        select(BreachRecord).where(BreachRecord.osint_report_id == report.id)
    )

    return {
        "id": str(report.id),
        "applicant_id": str(report.applicant_id),
        "trust_score": {
            "overall_trust_score": report.trust_score,
            "network_depth_score": report.network_depth_score,
            "footprint_longevity_score": report.footprint_longevity_score,
            "professional_consistency_score": report.professional_consistency_score,
            "identity_verification_score": report.identity_verification_score,
        } if report.trust_score else None,
        "total_platforms_found": report.total_platforms_found,
        "total_breaches_found": report.total_breaches_found,
        "identity_verified": report.identity_verified,
        "risk_flags": report.risk_flags,
        "scan_status": report.scan_status,
        "platform_matches": [
            {
                "platform_name": m.platform_name,
                "profile_url": m.profile_url,
                "found": m.found,
                "category": m.category,
            }
            for m in matches_result.scalars()
        ],
        "breach_records": [
            {
                "breach_name": b.breach_name,
                "breach_date": b.breach_date.isoformat() if b.breach_date else None,
                "pwn_count": b.pwn_count,
                "data_classes": b.data_classes,
            }
            for b in breaches_result.scalars()
        ],
    }


@router.post("/username-search", response_model=UsernameSearchResponse)
async def search_username(req: UsernameSearchRequest):
    """Search for a username across platforms using Sherlock Docker."""
    result = await sherlock_runner.search_username(req.username)
    return UsernameSearchResponse(
        username=result["username"],
        total_found=result["total_found"],
        total_checked=result["total_checked"],
        platforms=[PlatformMatchResponse(**p) for p in result["platforms"]],
    )


@router.post("/breach-check", response_model=BreachCheckResponse)
async def check_breach(req: BreachCheckRequest):
    """Check an email against HaveIBeenPwned breach database."""
    result = await breach_checker.check_email(req.email)
    return BreachCheckResponse(
        email=result["email"],
        total_breaches=result["total_breaches"],
        footprint_longevity_years=result.get("footprint_longevity_years"),
        breaches=[BreachRecordResponse(**b) for b in result["breaches"]],
    )


@router.post("/verify-identity", response_model=IdentityVerifyResponse)
async def verify_identity(req: IdentityVerifyRequest):
    """Verify government-issued identity documents."""
    result = await identity_verifier.verify_all(
        pan_number=req.pan_number,
        aadhaar_number=req.aadhaar_number,
        uan_number=req.uan_number,
        full_name=req.full_name,
    )
    return IdentityVerifyResponse(**result)
