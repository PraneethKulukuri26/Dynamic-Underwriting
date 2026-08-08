"""
Multi-Agent Orchestrator
LangGraph-based supervisor that coordinates all 5 agents for underwriting decisions.
Implements the Cooperating Agent Network pattern.
"""

import logging
import time
from typing import Dict, Any, Optional

from backend.agents.cashflow_agent import cashflow_agent
from backend.agents.osint_agent import osint_agent
from backend.agents.biometrics_agent import biometrics_agent
from backend.agents.selfcheck_agent import selfcheck_agent
from backend.agents.explainability_agent import explainability_agent
from backend.privacy.pii_redactor import pii_redactor
from backend.privacy.minor_exclusions import minor_exclusion_filter
from backend.privacy.ldp import ldp
from backend.privacy.budget_tracker import budget_tracker
from backend.config import settings

logger = logging.getLogger(__name__)

# Score weights for final decision
SCORE_WEIGHTS = {
    "cashflow": 0.35,
    "osint": 0.25,
    "biometrics": 0.25,
    "selfcheck_modifier": 0.15,
}

# Decision thresholds
APPROVE_THRESHOLD = 0.4   # Risk score below this = APPROVED
DENY_THRESHOLD = 0.7      # Risk score above this = DENIED
# Between thresholds = REVIEW_REQUIRED


class UnderwritingOrchestrator:
    """
    Supervisor-pattern orchestrator coordinating 5 specialized agents.
    Pipeline: Privacy Guardrails → Parallel Agents → Self-Check → Explainability → Decision
    """

    async def evaluate(
        self,
        applicant_id: str,
        financial_data: Optional[Dict] = None,
        osint_data: Optional[Dict] = None,
        biometrics_data: Optional[Dict] = None,
        baseline_bureau_score: Optional[float] = None,
        include_cashflow: bool = True,
        include_osint: bool = True,
        include_biometrics: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute the full multi-agent underwriting evaluation.

        Pipeline:
        1. Privacy Guardrails (PII redaction, minor exclusions, LDP noise)
        2. Parallel agent evaluation (Cash-Flow, OSINT, Biometrics)
        3. Self-Check audit (cost + business rules)
        4. Explainability (plain-language rationale)
        5. Final decision synthesis

        Returns:
            Complete underwriting decision with all agent outputs
        """
        start_time = time.time()
        agent_outputs = {}

        # === Step 1: Privacy Guardrails ===
        logger.info(f"[Orchestrator] Starting evaluation for applicant {applicant_id}")

        if financial_data:
            financial_data, fin_redactions = pii_redactor.redact_dict(financial_data)
            financial_data, fin_exclusions = minor_exclusion_filter.filter_dict(financial_data)

        if osint_data:
            osint_data, osint_redactions = pii_redactor.redact_dict(osint_data)
            osint_data, osint_exclusions = minor_exclusion_filter.filter_dict(osint_data)

        if biometrics_data:
            biometrics_data, bio_redactions = pii_redactor.redact_dict(biometrics_data)

        # Check privacy budget
        epsilon_per_query = settings.default_epsilon
        if not budget_tracker.can_query(applicant_id, epsilon_per_query * 3):
            logger.warning(f"Privacy budget insufficient for {applicant_id}")
            return self._budget_exhausted_response(applicant_id)

        # === Step 2: Parallel Agent Evaluation ===
        if include_cashflow and financial_data:
            logger.info("[Orchestrator] Running Cash-Flow Agent")
            agent_outputs["cashflow"] = await cashflow_agent.evaluate(financial_data)
            budget_tracker.record_query(applicant_id, epsilon_per_query, "cashflow_agent")

        if include_osint and osint_data:
            logger.info("[Orchestrator] Running OSINT Agent")
            agent_outputs["osint"] = await osint_agent.evaluate(osint_data)
            budget_tracker.record_query(applicant_id, epsilon_per_query, "osint_agent")

        if include_biometrics and biometrics_data:
            logger.info("[Orchestrator] Running Biometrics Agent")
            agent_outputs["biometrics"] = await biometrics_agent.evaluate(biometrics_data)
            budget_tracker.record_query(applicant_id, epsilon_per_query, "biometrics_agent")

        # === Step 3: Synthesize Risk Score ===
        synthesized_score = self._synthesize_score(agent_outputs, baseline_bureau_score)

        # === Step 4: Self-Check Audit ===
        logger.info("[Orchestrator] Running Self-Check Agent")
        selfcheck_result = selfcheck_agent.evaluate(
            agent_outputs, synthesized_score, baseline_bureau_score
        )
        agent_outputs["selfcheck"] = selfcheck_result

        # === Step 5: Determine Decision ===
        decision = self._make_decision(synthesized_score, selfcheck_result)

        # === Step 6: Explainability ===
        logger.info("[Orchestrator] Running Explainability Agent")
        privacy_spent = budget_tracker.get_budget_status(applicant_id).get("total_spent", 0)
        explanation = await explainability_agent.generate_explanations(
            decision, synthesized_score, agent_outputs, privacy_spent
        )
        agent_outputs["explainability"] = explanation

        # === Step 7: Compile Final Result ===
        elapsed_ms = int((time.time() - start_time) * 1000)
        total_tokens = sum(o.get("tokens_used", 0) for o in agent_outputs.values())
        total_cost = selfcheck_result.get("cost_analysis", {}).get("total_cost_usd", 0)

        # Calculate adjusted bureau score
        adjusted_bureau = None
        if baseline_bureau_score is not None:
            # Dynamic adjustment: shift bureau score based on alternative signals
            adjustment = (0.5 - synthesized_score) * 100  # ±50 points max
            adjusted_bureau = max(300, min(900, baseline_bureau_score + adjustment))

        result = {
            "applicant_id": applicant_id,
            "decision": decision,
            "final_risk_score": round(synthesized_score, 4),
            "adjusted_bureau_score": round(adjusted_bureau, 0) if adjusted_bureau else None,
            "confidence": selfcheck_result.get("confidence", 0.5),
            "cashflow_score": agent_outputs.get("cashflow", {}).get("score"),
            "osint_score": agent_outputs.get("osint", {}).get("score"),
            "biometric_score": agent_outputs.get("biometrics", {}).get("score"),
            "consumer_explanation": explanation.get("consumer_explanation"),
            "regulator_explanation": explanation.get("regulator_explanation"),
            "contributing_factors": explanation.get("contributing_factors", []),
            "total_cost_usd": round(total_cost, 6),
            "model_tier": settings.groq_model,
            "total_tokens_used": total_tokens,
            "agent_latency_ms": elapsed_ms,
            "requires_human_review": selfcheck_result.get("requires_human_review", False),
            "privacy_budget_spent": round(privacy_spent, 6),
            "agent_outputs": agent_outputs,
        }

        logger.info(
            f"[Orchestrator] Evaluation complete: decision={decision}, "
            f"risk={synthesized_score:.4f}, cost=${total_cost:.6f}, "
            f"latency={elapsed_ms}ms"
        )

        return result

    def _synthesize_score(
        self,
        agent_outputs: Dict[str, Dict],
        baseline_bureau_score: Optional[float],
    ) -> float:
        """
        Compute weighted risk score from agent outputs.
        Dynamically adjusts the traditional baseline.
        """
        weighted_sum = 0.0
        total_weight = 0.0

        for agent_name, weight in SCORE_WEIGHTS.items():
            if agent_name == "selfcheck_modifier":
                continue
            if agent_name in agent_outputs and "score" in agent_outputs[agent_name]:
                score = agent_outputs[agent_name]["score"]
                confidence = agent_outputs[agent_name].get("confidence", 0.5)
                # Weight by both assigned weight and agent confidence
                effective_weight = weight * confidence
                weighted_sum += score * effective_weight
                total_weight += effective_weight

        if total_weight > 0:
            synthesized = weighted_sum / total_weight
        else:
            synthesized = 0.5  # No data = neutral

        # If we have a baseline bureau score, blend it in
        if baseline_bureau_score is not None:
            # Normalize bureau score to 0-1 risk (higher bureau = lower risk)
            bureau_risk = 1.0 - ((baseline_bureau_score - 300) / 600)
            # 60% alternative data, 40% traditional bureau
            synthesized = 0.6 * synthesized + 0.4 * bureau_risk

        return max(0.0, min(1.0, synthesized))

    def _make_decision(self, score: float, selfcheck: Dict) -> str:
        """Determine final decision based on score and self-check flags."""
        if selfcheck.get("requires_human_review"):
            return "REVIEW_REQUIRED"
        if score <= APPROVE_THRESHOLD:
            return "APPROVED"
        elif score >= DENY_THRESHOLD:
            return "DENIED"
        else:
            return "REVIEW_REQUIRED"

    def _budget_exhausted_response(self, applicant_id: str) -> Dict:
        return {
            "applicant_id": applicant_id,
            "decision": "REVIEW_REQUIRED",
            "final_risk_score": 0.5,
            "confidence": 0.0,
            "consumer_explanation": "Your application requires manual review due to system privacy limits.",
            "regulator_explanation": "Privacy budget exhausted. Manual review required per DPDP Act compliance.",
            "requires_human_review": True,
            "agent_outputs": {},
            "total_cost_usd": 0.0,
            "total_tokens_used": 0,
        }


# Singleton
orchestrator = UnderwritingOrchestrator()
