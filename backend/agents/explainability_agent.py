"""
Explainability Agent
Converts complex risk signals into plain-language rationales.
Produces both consumer-facing and regulator-facing explanations.
"""

import json
import logging
from typing import Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from backend.config import settings

logger = logging.getLogger(__name__)

EXPLAINABILITY_PROMPT = """You are the Explainability Agent in an AI-driven underwriting system.

You must produce TWO plain-language explanations for a credit decision:

1. **Consumer Explanation**: Written for the applicant. Friendly, clear, non-technical.
   - Explain why they were approved/denied in simple terms
   - List the top 3-4 factors that influenced the decision
   - Do NOT reveal internal scoring mechanics or model names

2. **Regulator Explanation**: Written for RBI/GDPR compliance auditors. Technical but accessible.
   - Reference specific data sources used (Open Banking, OSINT, Biometrics)
   - Explain the weighting methodology
   - Demonstrate that protected characteristics were excluded
   - Confirm privacy-preserving measures were applied

Respond with ONLY a valid JSON object (no markdown, no code blocks):
{
    "consumer_explanation": "<plain-language explanation for the applicant>",
    "regulator_explanation": "<technical justification for regulators>",
    "contributing_factors": [
        {"factor": "<name>", "weight": <float>, "source": "<data source>", "impact": "POSITIVE|NEGATIVE|NEUTRAL", "details": "<explanation>"}
    ]
}"""


class ExplainabilityAgent:
    """Translates risk vectors into audit-ready plain-language rationale."""

    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None and settings.groq_api_key:
            self.llm = ChatGroq(
                model=settings.groq_model,
                temperature=0.3,  # Slightly higher for more natural language
                max_tokens=settings.groq_max_tokens,
                api_key=settings.groq_api_key,
            )
        return self.llm

    async def generate_explanations(
        self,
        decision: str,
        final_score: float,
        agent_outputs: Dict[str, Dict],
        privacy_budget_spent: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Generate consumer and regulator explanations.

        Args:
            decision: APPROVED, DENIED, or REVIEW_REQUIRED
            final_score: Final risk score
            agent_outputs: All agent outputs with scores and reasoning
            privacy_budget_spent: Cumulative epsilon spent

        Returns:
            Explanations with contributing factors
        """
        llm = self._get_llm()

        if llm is None:
            return self._heuristic_explain(decision, final_score, agent_outputs)

        try:
            context = json.dumps({
                "decision": decision,
                "final_risk_score": final_score,
                "agent_results": {
                    name: {
                        "score": output.get("score"),
                        "reasoning": output.get("reasoning"),
                        "factors": output.get("contributing_factors", []),
                    }
                    for name, output in agent_outputs.items()
                },
                "privacy_measures": {
                    "pii_redaction_applied": True,
                    "protected_characteristics_excluded": True,
                    "ldp_noise_applied": True,
                    "privacy_budget_spent": privacy_budget_spent,
                },
            }, indent=2)

            messages = [
                SystemMessage(content=EXPLAINABILITY_PROMPT),
                HumanMessage(content=f"Generate explanations for this decision:\n\n{context}"),
            ]

            response = await llm.ainvoke(messages)
            result = json.loads(response.content.strip())
            result["tokens_used"] = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
            result["model_used"] = settings.groq_model
            return result

        except Exception as e:
            logger.error(f"Explainability agent failed: {e}")
            return self._heuristic_explain(decision, final_score, agent_outputs)

    def _heuristic_explain(self, decision: str, score: float, agent_outputs: Dict) -> Dict:
        """Generate template-based explanations when LLM unavailable."""
        factors = []
        for name, output in agent_outputs.items():
            agent_score = output.get("score", 0.5)
            factors.append({
                "factor": name.replace("_", " ").title(),
                "weight": round(1.0 / max(len(agent_outputs), 1), 2),
                "source": name,
                "impact": "POSITIVE" if agent_score < 0.4 else "NEGATIVE" if agent_score > 0.6 else "NEUTRAL",
                "details": output.get("reasoning", "Assessment completed"),
            })

        if decision == "APPROVED":
            consumer = (
                "Your application has been approved. Our assessment found that your financial "
                "profile demonstrates consistent income, a verifiable digital identity, and "
                "genuine interaction patterns."
            )
        elif decision == "DENIED":
            consumer = (
                "After careful review, we are unable to approve your application at this time. "
                "Key factors include concerns about financial consistency and identity verification. "
                "You may reapply after addressing these areas."
            )
        else:
            consumer = (
                "Your application is under additional review. Our automated systems have flagged "
                "certain areas that require human verification. A representative will contact you shortly."
            )

        regulator = (
            f"Decision: {decision} (Risk Score: {score:.4f}). "
            f"Data sources: Open Banking (Finexer), OSINT (Sherlock/HIBP), Behavioral Biometrics (BiGRU/RF). "
            f"Protected characteristics (age, sex, caste, religion) were excluded via MinorExclusionFilter. "
            f"Local Differential Privacy (Gaussian mechanism) applied to all data inputs. "
            f"All PII redacted via regex before agent processing."
        )

        return {
            "consumer_explanation": consumer,
            "regulator_explanation": regulator,
            "contributing_factors": factors,
            "tokens_used": 0,
            "model_used": "template",
        }


explainability_agent = ExplainabilityAgent()
