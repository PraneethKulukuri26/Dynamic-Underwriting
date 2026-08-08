"""
OSINT Pipeline Schemas
Request/Response models for OSINT scanning, breach checking, and trust scoring.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# --- Scan Request ---

class OSINTScanRequest(BaseModel):
    """Request to initiate a full OSINT scan."""
    applicant_id: UUID
    email: Optional[str] = None
    phone: Optional[str] = None
    username: Optional[str] = None
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    uan_number: Optional[str] = None


class UsernameSearchRequest(BaseModel):
    """Request for Sherlock username lookup."""
    username: str = Field(..., min_length=1, max_length=128)


class BreachCheckRequest(BaseModel):
    """Request to check email against HIBP."""
    email: str


class IdentityVerifyRequest(BaseModel):
    """Request for government ID verification."""
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    uan_number: Optional[str] = None
    full_name: Optional[str] = None


# --- Responses ---

class PlatformMatchResponse(BaseModel):
    """Single platform match result from Sherlock."""
    platform_name: str
    profile_url: Optional[str]
    found: bool
    response_time_ms: Optional[int]
    category: Optional[str]

    model_config = {"from_attributes": True}


class BreachRecordResponse(BaseModel):
    """Single breach record from HIBP."""
    breach_name: str
    breach_date: Optional[datetime]
    pwn_count: Optional[int]
    data_classes: Optional[List[str]]
    is_verified: bool

    model_config = {"from_attributes": True}


class TrustScoreBreakdown(BaseModel):
    """Detailed trust score with component breakdown."""
    overall_trust_score: float = Field(..., ge=0.0, le=1.0)
    network_depth_score: float = Field(..., ge=0.0, le=1.0)
    footprint_longevity_score: float = Field(..., ge=0.0, le=1.0)
    professional_consistency_score: float = Field(..., ge=0.0, le=1.0)
    identity_verification_score: float = Field(..., ge=0.0, le=1.0)


class OSINTReportResponse(BaseModel):
    """Full OSINT scan report."""
    id: UUID
    applicant_id: UUID
    trust_score: Optional[TrustScoreBreakdown]
    total_platforms_found: int
    total_breaches_found: int
    oldest_breach_date: Optional[datetime]
    identity_verified: bool
    risk_flags: Optional[List[str]]
    platform_matches: List[PlatformMatchResponse]
    breach_records: List[BreachRecordResponse]
    scan_status: str
    scan_started_at: Optional[datetime]
    scan_completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class UsernameSearchResponse(BaseModel):
    """Username search results."""
    username: str
    total_found: int
    total_checked: int
    platforms: List[PlatformMatchResponse]


class BreachCheckResponse(BaseModel):
    """Breach check results for an email."""
    email: str
    total_breaches: int
    footprint_longevity_years: Optional[float]
    breaches: List[BreachRecordResponse]


class IdentityVerifyResponse(BaseModel):
    """Government ID verification results."""
    pan_verified: Optional[bool] = None
    aadhaar_verified: Optional[bool] = None
    uan_verified: Optional[bool] = None
    name_match_score: Optional[float] = None
    employment_history: Optional[List[dict]] = None
    verification_details: dict = {}
