"""
Consent & Financial Aggregation Schemas
Request/Response models for consent management and financial data endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# --- Consent Schemas ---

class ConsentInitiateRequest(BaseModel):
    """Request to initiate consent flow."""
    applicant_id: UUID
    scopes: List[str] = Field(default=["accounts", "balances", "transactions"])
    bank_id: Optional[str] = None


class ConsentInitiateResponse(BaseModel):
    """Response with authorization URL for user redirect."""
    consent_token_id: UUID
    authorization_url: str
    scopes: List[str]
    expires_in_seconds: int = 300


class ConsentCallbackRequest(BaseModel):
    """OAuth callback parameters."""
    code: str
    state: str
    consent_token_id: UUID


class ConsentStatusResponse(BaseModel):
    """Current status of a consent token."""
    consent_token_id: UUID
    applicant_id: UUID
    status: str
    scopes: List[str]
    created_at: datetime
    expires_at: Optional[datetime]
    bank_id: Optional[str]

    model_config = {"from_attributes": True}


class ConsentRevokeResponse(BaseModel):
    """Confirmation of consent revocation."""
    consent_token_id: UUID
    status: str = "REVOKED"
    revoked_at: datetime


# --- Financial Data Schemas ---

class AccountInfo(BaseModel):
    """Bank account information."""
    account_id: str
    bank_name: str
    account_type: str
    currency: str = "INR"
    current_balance: Optional[float] = None
    available_balance: Optional[float] = None


class Transaction(BaseModel):
    """Individual transaction record."""
    transaction_id: str
    date: datetime
    amount: float
    currency: str = "INR"
    type: str  # CREDIT or DEBIT
    description: str
    category: Optional[str] = None
    merchant: Optional[str] = None
    running_balance: Optional[float] = None


class EnrichedBalanceResponse(BaseModel):
    """Balance data with enrichment engine reconstruction."""
    account_id: str
    current_balance: float
    available_balance: float
    running_balance_history: List[dict]  # [{date, balance}]
    enrichment_applied: bool = False


class FinancialSummaryResponse(BaseModel):
    """Aggregated financial analysis."""
    applicant_id: UUID
    accounts: List[AccountInfo]
    total_credits_30d: float
    total_debits_30d: float
    avg_monthly_income: float
    income_regularity_score: float
    transaction_categories: dict
    transaction_count_30d: int


# --- Audit Schemas ---

class AuditLogEntry(BaseModel):
    """Audit log entry for regulatory compliance."""
    id: UUID
    action: str
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
