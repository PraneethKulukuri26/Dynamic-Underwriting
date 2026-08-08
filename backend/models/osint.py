"""
OSINT Pipeline ORM Models
Stores OSINT scan results: platform matches, breach records, and composite trust scores.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class OSINTReport(Base):
    """
    Composite OSINT report for an applicant.
    Aggregates signals from Sherlock, HIBP, and identity verification.
    """
    __tablename__ = "osint_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False, index=True)

    # Composite Trust Score (0.0 - 1.0)
    trust_score = Column(Float, nullable=True)
    network_depth_score = Column(Float, nullable=True)        # From Sherlock platform matches
    footprint_longevity_score = Column(Float, nullable=True)  # From breach history age
    professional_consistency_score = Column(Float, nullable=True)  # LinkedIn vs UAN correlation
    identity_verification_score = Column(Float, nullable=True)     # Gov ID verification

    # Summary
    total_platforms_found = Column(Integer, default=0)
    total_breaches_found = Column(Integer, default=0)
    oldest_breach_date = Column(DateTime(timezone=True), nullable=True)
    identity_verified = Column(Boolean, default=False)
    risk_flags = Column(JSON, nullable=True)  # List of flagged concerns

    scan_status = Column(String(32), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED
    scan_started_at = Column(DateTime(timezone=True), nullable=True)
    scan_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    applicant = relationship("Applicant", back_populates="osint_reports")
    platform_matches = relationship("PlatformMatch", back_populates="osint_report", cascade="all, delete-orphan")
    breach_records = relationship("BreachRecord", back_populates="osint_report", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<OSINTReport(applicant={self.applicant_id}, trust_score={self.trust_score})>"


class PlatformMatch(Base):
    """
    Individual platform match from Sherlock username enumeration.
    """
    __tablename__ = "platform_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    osint_report_id = Column(UUID(as_uuid=True), ForeignKey("osint_reports.id"), nullable=False, index=True)
    platform_name = Column(String(128), nullable=False)
    profile_url = Column(Text, nullable=True)
    username_queried = Column(String(128), nullable=False)
    found = Column(Boolean, default=False)
    response_time_ms = Column(Integer, nullable=True)
    category = Column(String(64), nullable=True)  # SOCIAL, PROFESSIONAL, GAMING, etc.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    osint_report = relationship("OSINTReport", back_populates="platform_matches")

    def __repr__(self):
        return f"<PlatformMatch(platform={self.platform_name}, found={self.found})>"


class BreachRecord(Base):
    """
    Breach record from HaveIBeenPwned API.
    Used to calculate footprint longevity score.
    """
    __tablename__ = "breach_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    osint_report_id = Column(UUID(as_uuid=True), ForeignKey("osint_reports.id"), nullable=False, index=True)
    breach_name = Column(String(128), nullable=False)
    breach_date = Column(DateTime(timezone=True), nullable=True)
    pwn_count = Column(Integer, nullable=True)
    data_classes = Column(JSON, nullable=True)  # ["Email addresses", "Passwords", etc.]
    description = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    osint_report = relationship("OSINTReport", back_populates="breach_records")

    def __repr__(self):
        return f"<BreachRecord(breach={self.breach_name}, date={self.breach_date})>"
