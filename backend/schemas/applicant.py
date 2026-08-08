"""
Applicant Schemas
Request/Response models for applicant registration and profiles.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID


class ApplicantCreateRequest(BaseModel):
    """Request to register a new applicant."""
    email: str = Field(..., description="Applicant email address")
    phone: Optional[str] = Field(None, description="Phone number with country code")
    full_name: Optional[str] = None
    username: Optional[str] = None
    pan_number: Optional[str] = Field(None, pattern=r"^[A-Z]{5}\d{4}[A-Z]$")
    aadhaar_number: Optional[str] = Field(None, description="12-digit Aadhaar (hashed before storage)")
    uan_number: Optional[str] = Field(None, pattern=r"^\d{12}$")
    declared_income: Optional[float] = None
    declared_employer: Optional[str] = None
    session_token: Optional[str] = Field(None, description="Biometric session token to link to this applicant")


class ApplicantResponse(BaseModel):
    """Applicant details response."""
    id: UUID
    email: str
    phone: Optional[str]
    full_name: Optional[str]
    username: Optional[str]
    application_status: str
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ApplicantSummary(BaseModel):
    """Lightweight applicant summary for lists."""
    id: UUID
    email: str
    full_name: Optional[str]
    application_status: str
    created_at: datetime

    model_config = {"from_attributes": True}
