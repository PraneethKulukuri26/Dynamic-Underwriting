"""
Underwriting Decision ORM Models
Stores multi-agent underwriting outputs, risk scores, and cost tracking.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, Float, Integer, Text, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class UnderwritingDecision(Base):
    """
    Final underwriting decision synthesized from all agent outputs.
    Includes plain-language explanations for consumers and regulators.
    """
    __tablename__ = "underwriting_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False, index=True)

    # Final decision
    decision = Column(String(32), nullable=False)  # APPROVED, DENIED, REVIEW_REQUIRED
    final_risk_score = Column(Float, nullable=False)  # 0.0 (low risk) - 1.0 (high risk)
    adjusted_bureau_score = Column(Float, nullable=True)  # Traditional score + dynamic adjustment
    confidence = Column(Float, nullable=True)

    # Agent-specific scores
    cashflow_score = Column(Float, nullable=True)
    osint_score = Column(Float, nullable=True)
    biometric_score = Column(Float, nullable=True)

    # Explainability
    consumer_explanation = Column(Text, nullable=True)    # Plain-language for applicant
    regulator_explanation = Column(Text, nullable=True)   # Technical justification for RBI/GDPR
    contributing_factors = Column(JSON, nullable=True)    # [{factor, weight, source, impact}]

    # Self-check / cost tracking
    total_cost_usd = Column(Float, default=0.0)           # Cost-per-decision
    model_tier = Column(String(32), nullable=True)         # "groq_llama70b", "groq_llama8b", "local_rf"
    total_tokens_used = Column(Integer, default=0)
    agent_latency_ms = Column(Integer, nullable=True)

    # Privacy
    privacy_budget_spent = Column(Float, default=0.0)

    # Status
    requires_human_review = Column(Boolean, default=False)
    human_override_decision = Column(String(32), nullable=True)
    human_reviewer_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    applicant = relationship("Applicant", back_populates="underwriting_decisions")
    agent_outputs = relationship("AgentOutput", back_populates="decision", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UnderwritingDecision(applicant={self.applicant_id}, decision={self.decision}, risk={self.final_risk_score})>"


class AgentOutput(Base):
    """
    Individual agent output within a multi-agent underwriting decision.
    One record per agent per decision.
    """
    __tablename__ = "agent_outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id = Column(UUID(as_uuid=True), ForeignKey("underwriting_decisions.id"), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False)  # cashflow, osint, biometrics, selfcheck, explainability
    agent_role = Column(String(128), nullable=True)

    # Output
    score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    raw_output = Column(JSON, nullable=True)
    contributing_factors = Column(JSON, nullable=True)

    # Cost tracking
    tokens_used = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    model_used = Column(String(64), nullable=True)
    latency_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    decision = relationship("UnderwritingDecision", back_populates="agent_outputs")

    def __repr__(self):
        return f"<AgentOutput(agent={self.agent_name}, score={self.score})>"


class RiskScore(Base):
    """
    Historical risk score tracking for continuous dynamic adjustment.
    Records score evolution as new signals arrive.
    """
    __tablename__ = "risk_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("applicants.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    score_type = Column(String(32), nullable=False)  # BASELINE, ADJUSTED, DYNAMIC
    adjustment_reason = Column(String(256), nullable=True)
    signal_source = Column(String(64), nullable=True)  # cashflow, osint, biometrics, etc.
    previous_score = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<RiskScore(applicant={self.applicant_id}, score={self.score}, type={self.score_type})>"
