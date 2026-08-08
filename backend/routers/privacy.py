"""
Privacy & Compliance Router
Module 4: PII redaction, LDP noise, privacy budget, and audit endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.privacy.pii_redactor import pii_redactor
from backend.privacy.ldp import ldp
from backend.privacy.budget_tracker import budget_tracker
from backend.privacy.minor_exclusions import minor_exclusion_filter
from backend.config import settings

router = APIRouter(prefix="/api/v1/privacy", tags=["Privacy & Compliance"])


class RedactRequest(BaseModel):
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class RedactResponse(BaseModel):
    redacted_text: Optional[str] = None
    redacted_data: Optional[Dict[str, Any]] = None
    redactions: List[Dict]
    total_pii_found: int


class NoiseRequest(BaseModel):
    values: List[float]
    epsilon: float = Field(default=1.0, gt=0)
    delta: float = Field(default=1e-5, gt=0, lt=1)
    sensitivity: float = Field(default=1.0, ge=0)


class NoiseResponse(BaseModel):
    original_values: List[float]
    noised_values: List[float]
    epsilon_used: float
    noise_scale_sigma: float


@router.post("/redact", response_model=RedactResponse)
async def redact_pii(req: RedactRequest):
    """Redact PII from text or structured data."""
    redacted_text = None
    redacted_data = None
    all_redactions = []

    if req.text:
        redacted_text, redactions = pii_redactor.redact_text(req.text)
        all_redactions.extend(redactions)

    if req.data:
        redacted_data, redactions = pii_redactor.redact_dict(req.data)
        all_redactions.extend(redactions)

    return RedactResponse(
        redacted_text=redacted_text,
        redacted_data=redacted_data,
        redactions=all_redactions,
        total_pii_found=len(all_redactions),
    )


@router.post("/noise", response_model=NoiseResponse)
async def apply_noise(req: NoiseRequest):
    """Apply LDP Gaussian noise to data values."""
    sigma = ldp.compute_noise_scale(req.sensitivity, req.epsilon, req.delta)
    noised = ldp.add_noise(req.values, req.epsilon, req.delta, req.sensitivity)

    return NoiseResponse(
        original_values=req.values,
        noised_values=noised.tolist() if hasattr(noised, 'tolist') else [float(noised)],
        epsilon_used=req.epsilon,
        noise_scale_sigma=round(sigma, 6),
    )


@router.get("/budget/{applicant_id}")
async def get_privacy_budget(applicant_id: str):
    """Check privacy budget status for an applicant."""
    return budget_tracker.get_budget_status(applicant_id)


@router.post("/filter-protected")
async def filter_protected_fields(data: Dict[str, Any]):
    """Remove protected characteristics from data."""
    filtered, exclusions = minor_exclusion_filter.filter_dict(data)
    return {
        "filtered_data": filtered,
        "exclusions": exclusions,
        "total_excluded": len(exclusions),
    }


@router.get("/audit-log")
async def get_audit_log():
    """Get privacy operation summary."""
    return {
        "privacy_config": {
            "default_epsilon": settings.default_epsilon,
            "default_delta": settings.default_delta,
            "max_privacy_budget": settings.max_privacy_budget,
            "gradient_clip_norm": settings.gradient_clip_norm,
        },
        "supported_operations": [
            "PII Redaction (Regex)",
            "LDP Gaussian Noise",
            "LDP Laplace Noise",
            "Gradient Clipping (L2 Norm)",
            "Privacy Budget Tracking (RDP)",
            "Minor Exclusion Filtering",
            "SMPC Additive Secret Sharing",
            "Paillier Homomorphic Encryption (Stub)",
        ],
    }
