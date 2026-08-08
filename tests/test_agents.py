"""
Tests for Agent System
Covers: Self-Check Agent, Orchestrator Logic
"""

import pytest
from backend.agents.selfcheck_agent import SelfCheckAgent, selfcheck_agent, GROQ_PRICING, AI_DEPTH_WEIGHT
from backend.agents.orchestrator import (
    UnderwritingOrchestrator, orchestrator,
    SCORE_WEIGHTS, APPROVE_THRESHOLD, DENY_THRESHOLD
)


# ============================================================
# SELF-CHECK AGENT TESTS
# ============================================================

class TestSelfCheckAgent:
    """Tests for the Self-Check business rule auditor."""

    def test_evaluate_basic(self):
        """Basic evaluation should return valid structure."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.3, "confidence": 0.8, "tokens_used": 100, "model_used": "llama-3.3-70b-versatile"},
            "osint": {"score": 0.4, "confidence": 0.7, "tokens_used": 80, "model_used": "llama-3.3-70b-versatile"},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.35)

        assert "score" in result
        assert "confidence" in result
        assert "requires_human_review" in result
        assert "review_flags" in result
        assert "cost_analysis" in result
        assert "ai_depth_score" in result

    def test_requires_review_set_on_high_disagreement(self):
        """requires_review should be True when agents disagree significantly."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.1, "confidence": 0.8},
            "osint": {"score": 0.9, "confidence": 0.8},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.5)

        assert result["requires_human_review"] is True
        assert "HIGH_AGENT_DISAGREEMENT" in result["review_flags"]

    def test_requires_review_set_on_high_risk(self):
        """requires_review should be True for high-risk scores."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.8, "confidence": 0.8},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.8)

        assert result["requires_human_review"] is True
        assert "HIGH_RISK_SCORE" in result["review_flags"]

    def test_requires_review_set_on_high_cost(self):
        """requires_review should be True when cost is high."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.3, "confidence": 0.8, "tokens_used": 50000, "model_used": "llama-3.3-70b-versatile"},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.3)

        assert result["requires_human_review"] is True
        assert "HIGH_COST_DECISION" in result["review_flags"]

    def test_no_flags_low_risk(self):
        """Low-risk, low-cost evaluation should have no flags."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.2, "confidence": 0.8, "tokens_used": 100, "model_used": "heuristic"},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.2)

        assert result["requires_human_review"] is False
        assert len(result["review_flags"]) == 0

    def test_calculate_cost_70b(self):
        """Cost calculation for 70b model should use correct pricing."""
        agent = SelfCheckAgent()
        cost = agent._calculate_cost(tokens=1000, model="llama-3.3-70b-versatile")
        # 600 input tokens * 0.59/1M + 400 output * 0.79/1M
        expected = (600 * 0.59 + 400 * 0.79) / 1_000_000
        assert cost == pytest.approx(expected, abs=0.0001)

    def test_calculate_cost_heuristic(self):
        """Heuristic model should have zero cost."""
        agent = SelfCheckAgent()
        cost = agent._calculate_cost(tokens=1000, model="heuristic")
        assert cost == 0.0

    def test_scrub_protected_characteristics(self):
        """Protected characteristics should be redacted from text."""
        agent = SelfCheckAgent()
        text = "The applicant is a 30 year old male hindu"
        scrubbed = agent._scrub_protected_characteristics(text)

        assert "male" not in scrubbed.lower() or "[REDACTED]" in scrubbed
        assert "hindu" not in scrubbed.lower() or "[REDACTED]" in scrubbed

    def test_scrub_empty_text(self):
        """Empty text should pass through."""
        agent = SelfCheckAgent()
        assert agent._scrub_protected_characteristics("") == ""
        assert agent._scrub_protected_characteristics(None) is None

    def test_calculate_ai_depth(self):
        """AI depth should be ratio of LLM agents to total."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"model_used": "llama-3.3-70b-versatile"},
            "osint": {"model_used": "llama-3.3-70b-versatile"},
            "biometrics": {"model_used": "heuristic"},
        }
        depth = agent._calculate_ai_depth(agent_outputs)
        assert depth == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_recommend_tier_low_risk(self):
        """Low risk should recommend smaller model."""
        agent = SelfCheckAgent()
        rec = agent._recommend_tier(current_cost=0.001, risk_score=0.2)
        assert "smaller model" in rec.lower() or "8b" in rec

    def test_recommend_tier_high_risk(self):
        """High risk should recommend full model."""
        agent = SelfCheckAgent()
        rec = agent._recommend_tier(current_cost=0.01, risk_score=0.8)
        assert "full model" in rec.lower() or "70b" in rec

    def test_cost_analysis_structure(self):
        """Cost analysis should contain expected fields."""
        agent = SelfCheckAgent()
        agent_outputs = {
            "cashflow": {"score": 0.3, "tokens_used": 100, "model_used": "heuristic"},
        }
        result = agent.evaluate(agent_outputs, synthesized_score=0.3)
        cost_analysis = result["cost_analysis"]

        assert "total_cost_usd" in cost_analysis
        assert "total_tokens" in cost_analysis
        assert "per_agent_costs" in cost_analysis
        assert "cost_efficiency" in cost_analysis

    def test_empty_agent_outputs(self):
        """Empty agent outputs should be handled gracefully."""
        agent = SelfCheckAgent()
        result = agent.evaluate({}, synthesized_score=0.5)

        assert result["score"] == 0.5
        assert result["requires_human_review"] is False


# ============================================================
# ORCHESTRATOR LOGIC TESTS
# ============================================================

class TestOrchestratorLogic:
    """Tests for orchestrator decision logic (without LLM calls)."""

    def test_synthesize_score_weighted_average(self):
        """Score synthesis should use weighted average."""
        orch = UnderwritingOrchestrator()
        agent_outputs = {
            "cashflow": {"score": 0.3, "confidence": 1.0},
            "osint": {"score": 0.5, "confidence": 1.0},
            "biometrics": {"score": 0.7, "confidence": 1.0},
        }
        score = orch._synthesize_score(agent_outputs, baseline_bureau_score=None)
        # 0.35*0.3 + 0.25*0.5 + 0.25*0.7 = 0.105 + 0.125 + 0.175 = 0.405
        expected = 0.35 * 0.3 + 0.25 * 0.5 + 0.25 * 0.7
        # Normalized by total weight (0.85 since selfcheck not included)
        expected_normalized = expected / 0.85
        assert score == pytest.approx(expected_normalized, abs=0.01)

    def test_synthesize_score_with_bureau(self):
        """Bureau score should blend 60/40 with alternative data."""
        orch = UnderwritingOrchestrator()
        agent_outputs = {
            "cashflow": {"score": 0.3, "confidence": 1.0},
        }
        # Bureau 700 -> normalized risk = 1 - (700-300)/600 = 0.333
        score = orch._synthesize_score(agent_outputs, baseline_bureau_score=700)
        # 0.6 * alt_score + 0.4 * bureau_risk
        assert 0.0 <= score <= 1.0

    def test_synthesize_score_no_data(self):
        """No agent outputs should return neutral score."""
        orch = UnderwritingOrchestrator()
        score = orch._synthesize_score({}, baseline_bureau_score=None)
        assert score == 0.5

    def test_make_decision_approve(self):
        """Score below approve threshold should return APPROVED."""
        orch = UnderwritingOrchestrator()
        selfcheck = {"requires_human_review": False}
        decision = orch._make_decision(0.3, selfcheck)
        assert decision == "APPROVED"

    def test_make_decision_deny(self):
        """Score above deny threshold should return DENIED."""
        orch = UnderwritingOrchestrator()
        selfcheck = {"requires_human_review": False}
        decision = orch._make_decision(0.8, selfcheck)
        assert decision == "DENIED"

    def test_make_decision_review_between(self):
        """Score between thresholds should return REVIEW_REQUIRED."""
        orch = UnderwritingOrchestrator()
        selfcheck = {"requires_human_review": False}
        decision = orch._make_decision(0.55, selfcheck)
        assert decision == "REVIEW_REQUIRED"

    def test_make_decision_review_flagged(self):
        """Self-check flag should trigger REVIEW_REQUIRED."""
        orch = UnderwritingOrchestrator()
        selfcheck = {"requires_human_review": True}
        decision = orch._make_decision(0.3, selfcheck)  # Low score but flagged
        assert decision == "REVIEW_REQUIRED"

    def test_budget_exhausted_response(self):
        """Budget exhausted should return REVIEW_REQUIRED with zero cost."""
        orch = UnderwritingOrchestrator()
        result = orch._budget_exhausted_response("test_applicant")

        assert result["decision"] == "REVIEW_REQUIRED"
        assert result["total_cost_usd"] == 0.0
        assert result["requires_human_review"] is True

    def test_score_weights_sum(self):
        """Score weights should be defined correctly."""
        assert SCORE_WEIGHTS["cashflow"] == 0.35
        assert SCORE_WEIGHTS["osint"] == 0.25
        assert SCORE_WEIGHTS["biometrics"] == 0.25
        assert SCORE_WEIGHTS["selfcheck_modifier"] == 0.15

    def test_thresholds_defined(self):
        """Decision thresholds should be defined."""
        assert APPROVE_THRESHOLD == 0.4
        assert DENY_THRESHOLD == 0.7
        assert APPROVE_THRESHOLD < DENY_THRESHOLD

    def test_synthesize_score_clamped(self):
        """Score should be clamped to [0, 1]."""
        orch = UnderwritingOrchestrator()
        # Extreme bureau score
        score = orch._synthesize_score({}, baseline_bureau_score=300)
        assert 0.0 <= score <= 1.0
        score = orch._synthesize_score({}, baseline_bureau_score=900)
        assert 0.0 <= score <= 1.0
