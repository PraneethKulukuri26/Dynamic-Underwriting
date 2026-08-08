"""
Consent & Financial Aggregation Router
Module 1: Consent management, financial data retrieval, and balance enrichment.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.schemas.consent import (
    ConsentInitiateRequest, ConsentInitiateResponse,
    ConsentStatusResponse, ConsentRevokeResponse,
    FinancialSummaryResponse, AccountInfo, EnrichedBalanceResponse,
)
from backend.schemas.applicant import ApplicantCreateRequest, ApplicantResponse
from backend.models.consent import ConsentToken, ConsentStatus
from backend.models.applicant import Applicant, FinancialProfile
from backend.services.consent_manager import consent_manager
from backend.services.finexer_client import finexer_client
from backend.services.balance_enrichment import balance_enrichment

import hashlib
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["Consent & Financial"])


@router.post("/applicants", response_model=ApplicantResponse)
async def create_applicant(req: ApplicantCreateRequest, db: AsyncSession = Depends(get_db)):
    """Register a new applicant."""
    # Check if applicant already exists by email
    result = await db.execute(select(Applicant).where(Applicant.email == req.email))
    existing = result.scalar_one_or_none()
    if existing:
        if req.session_token:
            from backend.models.biometrics import BiometricSession
            session_result = await db.execute(
                select(BiometricSession).where(BiometricSession.session_token == req.session_token)
            )
            bio_session = session_result.scalar_one_or_none()
            if bio_session:
                bio_session.applicant_id = existing.id
        return existing

    # Hash sensitive fields
    aadhaar_hash = None
    if req.aadhaar_number:
        aadhaar_hash = hashlib.sha256(req.aadhaar_number.encode()).hexdigest()

    applicant = Applicant(
        email=req.email,
        phone=req.phone,
        full_name=req.full_name,
        username=req.username,
        pan_number=req.pan_number,
        aadhaar_hash=aadhaar_hash,
        uan_number=req.uan_number,
        declared_income=req.declared_income,
        declared_employer=req.declared_employer,
    )
    db.add(applicant)
    await db.flush()
    await db.refresh(applicant)
    
    # Link biometric session if provided
    if req.session_token:
        from backend.models.biometrics import BiometricSession
        session_result = await db.execute(
            select(BiometricSession).where(BiometricSession.session_token == req.session_token)
        )
        bio_session = session_result.scalar_one_or_none()
        if bio_session:
            bio_session.applicant_id = applicant.id

    return applicant


@router.post("/consent/initiate", response_model=ConsentInitiateResponse)
async def initiate_consent(
    req: ConsentInitiateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate consent flow: generates authorization URL for bank redirect."""
    consent = await consent_manager.create_consent(
        db=db,
        applicant_id=req.applicant_id,
        scopes=req.scopes,
        bank_id=req.bank_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    auth_url = consent.authorization_url or ""
    if "mock_bank.html" in auth_url:
        auth_url = f"{auth_url}?state={consent.id}"

    return ConsentInitiateResponse(
        consent_token_id=consent.id,
        authorization_url=auth_url,
        scopes=consent.scopes,
    )


@router.get("/consent/callback")
async def consent_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback: exchange authorization code for access tokens."""
    try:
        consent_token_id = uuid.UUID(state)
    except ValueError:
        raise HTTPException(400, "Invalid state parameter")

    consent = await consent_manager.activate_consent(
        db=db,
        consent_token_id=consent_token_id,
        auth_code=code,
    )

    return {"status": "activated", "consent_token_id": str(consent.id)}


class MockAuthorizeRequest(BaseModel):
    consent_token_id: uuid.UUID

@router.post("/consent/mock-authorize")
async def mock_authorize(
    req: MockAuthorizeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mock endpoint to authorize and generate LLM data."""
    # Ensure it's a mock token
    result = await db.execute(select(ConsentToken).where(ConsentToken.id == req.consent_token_id))
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(404, "Consent token not found")

    # Fetch applicant to get declared income for LLM prompt
    applicant_result = await db.execute(select(Applicant).where(Applicant.id == consent.applicant_id))
    applicant = applicant_result.scalar_one_or_none()
    income = applicant.declared_income if applicant and applicant.declared_income else 50000.0
    name = applicant.full_name if applicant and applicant.full_name else "John Doe"

    # Activate consent and trigger AI data generation
    await finexer_client.mock_authorize(req.consent_token_id, income, name)
    
    consent.status = ConsentStatus.ACTIVE
    consent.access_token = f"mock_access_{req.consent_token_id.hex}"

    return {"status": "success"}


@router.post("/consent/revoke/{token_id}", response_model=ConsentRevokeResponse)
async def revoke_consent(
    token_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Immediately revoke consent and nullify all tokens."""
    try:
        consent = await consent_manager.revoke_consent(
            db=db,
            consent_token_id=token_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as e:
        raise HTTPException(404, str(e))

    return ConsentRevokeResponse(
        consent_token_id=consent.id,
        revoked_at=consent.revoked_at,
    )


@router.get("/consent/status/{token_id}", response_model=ConsentStatusResponse)
async def get_consent_status(token_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Check consent token status."""
    result = await db.execute(select(ConsentToken).where(ConsentToken.id == token_id))
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(404, "Consent token not found")

    # Check expiration
    await consent_manager.check_expiration(db, token_id)

    return consent


@router.get("/financial/accounts/{applicant_id}")
async def get_accounts(applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get linked bank accounts for an applicant."""
    consent = await consent_manager.get_active_consent(db, applicant_id)
    if not consent:
        raise HTTPException(404, "No active consent found for this applicant")

    accounts = await finexer_client.get_accounts(consent.access_token or "")
    return {"applicant_id": str(applicant_id), "accounts": accounts}


@router.get("/financial/transactions/{account_id}")
async def get_transactions(account_id: str, applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get enriched transactions for an account."""
    consent = await consent_manager.get_active_consent(db, applicant_id)
    if not consent:
        raise HTTPException(404, "No active consent found")

    transactions = await finexer_client.get_transactions(consent.access_token or "", account_id)

    # Enrich with categories
    for txn in transactions:
        if not txn.get("category"):
            txn["category"] = balance_enrichment.categorize_transaction(txn.get("description", ""))

    # Analyze financial health
    analysis = balance_enrichment.analyze_financial_health(transactions)

    return {
        "account_id": account_id,
        "transactions": transactions,
        "analysis": analysis,
    }


@router.get("/financial/balances/{account_id}")
async def get_balances(account_id: str, applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get enriched balances with running balance reconstruction."""
    consent = await consent_manager.get_active_consent(db, applicant_id)
    if not consent:
        raise HTTPException(404, "No active consent found")

    balances = await finexer_client.get_balances(consent.access_token or "", account_id)
    transactions = await finexer_client.get_transactions(consent.access_token or "", account_id)

    # Reconstruct running balances
    running_balances = balance_enrichment.reconstruct_running_balances(
        transactions, balances.get("current_balance")
    )

    return {
        "account_id": account_id,
        "current_balance": balances.get("current_balance"),
        "available_balance": balances.get("available_balance"),
        "running_balance_history": running_balances,
        "enrichment_applied": True,
    }
