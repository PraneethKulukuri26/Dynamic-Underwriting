"""
Applicant & Financial Profile ORM Models
Core applicant record and aggregated financial data from Finexer.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Float, Text, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class Applicant(Base):
    """
    Primary applicant record.
    Central entity linking consent, OSINT, biometrics, and underwriting data.
    """
    __tablename__ = "applicants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    full_name = Column(String(255), nullable=True)
    username = Column(String(128), nullable=True, index=True)
    date_of_birth = Column(String(10), nullable=True)  # Stored redacted after processing
    pan_number = Column(String(10), nullable=True)      # Stored hashed
    aadhaar_hash = Column(String(64), nullable=True)     # SHA-256 hash only, never raw
    uan_number = Column(String(12), nullable=True)
    declared_income = Column(Float, nullable=True)
    declared_employer = Column(String(255), nullable=True)
    application_status = Column(String(32), default="PENDING", index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    consent_tokens = relationship("ConsentToken", back_populates="applicant", cascade="all, delete-orphan")
    financial_profiles = relationship("FinancialProfile", back_populates="applicant", cascade="all, delete-orphan")
    osint_reports = relationship("OSINTReport", back_populates="applicant", cascade="all, delete-orphan")
    biometric_sessions = relationship("BiometricSession", back_populates="applicant", cascade="all, delete-orphan")
    underwriting_decisions = relationship("UnderwritingDecision", back_populates="applicant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Applicant(id={self.id}, email={self.email})>"


class FinancialProfile(Base):
    """
    Aggregated financial data from Finexer Open Banking APIs.
    Includes enriched balances and categorized transactions.
    """
    __tablename__ = "financial_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False, index=True)
    account_id = Column(String(128), nullable=False)
    bank_name = Column(String(128), nullable=True)
    account_type = Column(String(32), nullable=True)  # SAVINGS, CURRENT, etc.
    currency = Column(String(3), default="INR")

    # Enriched balance data
    current_balance = Column(Float, nullable=True)
    available_balance = Column(Float, nullable=True)
    running_balance_history = Column(JSON, nullable=True)  # List of {date, balance} from enrichment engine

    # Aggregated transaction analysis
    total_credits_30d = Column(Float, default=0.0)
    total_debits_30d = Column(Float, default=0.0)
    avg_monthly_income = Column(Float, nullable=True)
    income_regularity_score = Column(Float, nullable=True)  # 0.0-1.0
    transaction_categories = Column(JSON, nullable=True)     # {category: total_amount}
    transaction_count_30d = Column(Integer, default=0)
    raw_transactions = Column(JSON, nullable=True)           # Cached raw transaction data

    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    applicant = relationship("Applicant", back_populates="financial_profiles",
                             foreign_keys=[applicant_id],
                             primaryjoin="FinancialProfile.applicant_id == Applicant.id")

    def __repr__(self):
        return f"<FinancialProfile(applicant={self.applicant_id}, bank={self.bank_name})>"
