"""
Consent Management ORM Models
Tracks consent tokens, scopes, and audit logs for BSA/AML compliance.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base
import enum


class ConsentStatus(str, enum.Enum):
    """Consent token lifecycle states."""
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ConsentToken(Base):
    """
    Represents a consent token for Open Banking data access.
    Maps to Finexer OAuth consent flow with time-bound permissions.
    """
    __tablename__ = "consent_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False, index=True)
    access_token = Column(String(512), nullable=True)
    refresh_token = Column(String(512), nullable=True)
    scopes = Column(JSON, nullable=False, default=list)  # ["accounts", "balances", "transactions"]
    status = Column(SAEnum(ConsentStatus), default=ConsentStatus.PENDING, nullable=False, index=True)
    authorization_url = Column(Text, nullable=True)
    callback_code = Column(String(256), nullable=True)
    bank_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    applicant = relationship("Applicant", back_populates="consent_tokens")
    audit_logs = relationship("AuditLog", back_populates="consent_token", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ConsentToken(id={self.id}, applicant={self.applicant_id}, status={self.status})>"


class AuditLog(Base):
    """
    Immutable audit trail for consent operations.
    Required for BSA/AML regulatory scrutiny and GDPR compliance.
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consent_token_id = Column(UUID(as_uuid=True), ForeignKey("consent_tokens.id"), nullable=True, index=True)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False)  # CONSENT_CREATED, TOKEN_EXCHANGED, REVOKED, DATA_ACCESSED, etc.
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    consent_token = relationship("ConsentToken", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog(action={self.action}, timestamp={self.timestamp})>"
