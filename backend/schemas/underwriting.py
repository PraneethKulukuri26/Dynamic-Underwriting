"""
Underwriting Decision Schemas
Request/Response models for the multi-agent underwriting core.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# --- Evaluation Request ---

class UnderwritingEvaluateRequest(BaseModel):
    """Request to trigger full multi-agent underwriting evaluation."""
    applicant_id: UUID
    include_cashflow: bool = True
    include_osint: bool = True
    include_biometrics: bool = True
    baseline_bureau_score: Optional[float] = Field(None, ge=300, le=900, description="Traditional credit score")
    force_model_tier: Optional[str] = Field(None, description="Override model: 'groq_llama70b', 'groq_llama8b'")


class AdjustScoreRequest(BaseModel):
    """Request to dynamically adjust risk score with new signals."""
    applicant_id: UUID
    signal_source: str
    adjustment_reason: str
    new_data: dict


# --- Agent Output Schemas ---

class AgentOutputResponse(BaseModel):
    """Individual agent output."""
    agent_name: str
    score: Optional[float]
    confidence: Optional[float]
    reasoning: Optional[str]
    contributing_factors: Optional[List[dict]]
    tokens_used: int
    cost_usd: float
    model_used: Optional[str]
    latency_ms: Optional[int]

    model_config = {"from_attributes": True}


class ContributingFactor(BaseModel):
    """A single factor contributing to the decision."""
    factor: str
    weight: float
    source: str
    impact: str  # POSITIVE, NEGATIVE, NEUTRAL
    details: Optional[str] = None


# --- Decision Response ---

class UnderwritingDecisionResponse(BaseModel):
    """Full underwriting decision with explanations."""
    id: UUID
    applicant_id: UUID
    decision: str
    final_risk_score: float
    adjusted_bureau_score: Optional[float]
    confidence: Optional[float]

    # Per-agent scores
    cashflow_score: Optional[float]
    osint_score: Optional[float]
    biometric_score: Optional[float]

    # Explanations
    consumer_explanation: Optional[str]
    regulator_explanation: Optional[str]
    contributing_factors: Optional[List[ContributingFactor]]

    # Cost & performance
    total_cost_usd: float
    model_tier: Optional[str]
    total_tokens_used: int
    agent_latency_ms: Optional[int]

    # Agent details
    agent_outputs: List[AgentOutputResponse]

    # Meta
    requires_human_review: bool
    privacy_budget_spent: float
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Cost Report ---

class CostReportEntry(BaseModel):
    """Cost data for a single decision."""
    decision_id: UUID
    applicant_id: UUID
    model_tier: Optional[str]
    total_cost_usd: float
    total_tokens_used: int
    agent_latency_ms: Optional[int]
    created_at: datetime


class CostReportResponse(BaseModel):
    """Aggregate cost-per-decision analytics."""
    total_decisions: int
    avg_cost_per_decision: float
    total_cost_usd: float
    avg_tokens_per_decision: float
    avg_latency_ms: float
    cost_by_model_tier: dict
    recent_decisions: List[CostReportEntry]


# --- Risk Score History ---

class RiskScoreHistoryEntry(BaseModel):
    """Historical risk score entry."""
    score: float
    score_type: str
    signal_source: Optional[str]
    adjustment_reason: Optional[str]
    previous_score: Optional[float]
    delta: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}
