"""
Self-Check Agent
Audits synthesized outputs against business impact goals.
Tracks cost-per-decision and model tier optimization.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Groq pricing (approximate, as of 2025)
GROQ_PRICING = {
    "llama-3.3-70b-versatile": {"input_per_1m": 0.59, "output_per_1m": 0.79},
    "llama-3.1-8b-instant": {"input_per_1m": 0.05, "output_per_1m": 0.08},
    "mixtral-8x7b-32768": {"input_per_1m": 0.24, "output_per_1m": 0.24},
    "heuristic": {"input_per_1m": 0.0, "output_per_1m": 0.0},
}

# Business impact weights (from spec: 20% AI Depth)
AI_DEPTH_WEIGHT = 0.20


class SelfCheckAgent:
    """
    Business impact auditor and cost optimizer.
    Validates decisions against business rules and tracks economics.
    """

    def evaluate(
        self,
        agent_outputs: Dict[str, Dict],
        synthesized_score: float,
        baseline_bureau_score: float = None,
    ) -> Dict[str, Any]:
        """
        Audit the multi-agent decision.

        Args:
            agent_outputs: Dict mapping agent_name -> agent output
            synthesized_score: Combined risk score
            baseline_bureau_score: Traditional credit score (300-900)

        Returns:
            Audit result with cost analysis and recommendations
        """
        # Calculate total cost
        total_tokens = 0
        total_cost = 0.0
        agent_costs = {}

        for agent_name, output in agent_outputs.items():
            tokens = output.get("tokens_used", 0)
            model = output.get("model_used", "heuristic")
            cost = self._calculate_cost(tokens, model)

            # Scrub reasoning for GDPR/DPDP compliance
            if "reasoning" in output:
                output["reasoning"] = self._scrub_protected_characteristics(output["reasoning"])
            if "contributing_factors" in output:
                for factor in output["contributing_factors"]:
                    if "details" in factor:
                        factor["details"] = self._scrub_protected_characteristics(factor["details"])

            total_tokens += tokens
            total_cost += cost
            agent_costs[agent_name] = {
                "tokens": tokens,
                "cost_usd": round(cost, 6),
                "model": model,
            }

        # Business rule validation
        requires_review = False
        flags = []

        # Flag if agents significantly disagree
        scores = [o.get("score", 0.5) for o in agent_outputs.values() if "score" in o]
        if scores:
            score_range = max(scores) - min(scores)
            if score_range > 0.4:
                flags.append("HIGH_AGENT_DISAGREEMENT")
                requires_review = True

        # Flag high-risk decisions
        if synthesized_score > 0.7:
            flags.append("HIGH_RISK_SCORE")
            requires_review = True

        # Flag if cost is unusually high
        if total_cost > 0.01:  # More than 1 cent per decision
            flags.append("HIGH_COST_DECISION")
            requires_review = True

        # AI Depth compliance check
        ai_depth_score = self._calculate_ai_depth(agent_outputs)

        # Model tier recommendation
        recommendation = self._recommend_tier(total_cost, synthesized_score)

        return {
            "score": round(synthesized_score, 4),
            "confidence": round(1.0 - (score_range / 2 if scores else 0.5), 4),
            "reasoning": f"Self-check: {len(flags)} flags raised. Cost: ${total_cost:.6f}",
            "requires_human_review": requires_review,
            "review_flags": flags,
            "cost_analysis": {
                "total_cost_usd": round(total_cost, 6),
                "total_tokens": total_tokens,
                "per_agent_costs": agent_costs,
                "cost_efficiency": recommendation,
            },
            "ai_depth_score": round(ai_depth_score, 4),
            "ai_depth_weight": AI_DEPTH_WEIGHT,
            "tokens_used": 0,
            "model_used": "selfcheck_logic",
        }

    def _calculate_cost(self, tokens: int, model: str) -> float:
        """Calculate USD cost for token usage on a model."""
        pricing = GROQ_PRICING.get(model, GROQ_PRICING.get("heuristic", {}))
        # Approximate 50/50 input/output split
        input_tokens = tokens * 0.6
        output_tokens = tokens * 0.4
        cost = (input_tokens * pricing.get("input_per_1m", 0) +
                output_tokens * pricing.get("output_per_1m", 0)) / 1_000_000
        return cost

    def _scrub_protected_characteristics(self, text: str) -> str:
        """
        Scan and redact protected characteristics to comply with GDPR/DPDP.
        """
        if not text:
            return text
            
        import re
        protected_keywords = [
            "age", "gender", "male", "female", "man", "woman", 
            "religion", "hindu", "muslim", "christian", "sikh", 
            "caste", "political", "race", "ethnicity"
        ]
        
        scrubbed = text
        for kw in protected_keywords:
            pattern = re.compile(rf"\b{kw}\b", re.IGNORECASE)
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
            
        return scrubbed

    def _calculate_ai_depth(self, agent_outputs: Dict) -> float:
        """Calculate AI Depth score (how much reasoning was applied)."""
        llm_agents = sum(1 for o in agent_outputs.values() if o.get("model_used") != "heuristic")
        total_agents = max(len(agent_outputs), 1)
        return llm_agents / total_agents

    def _recommend_tier(self, current_cost: float, risk_score: float) -> str:
        """Recommend model tier based on cost and risk level."""
        if risk_score < 0.3:
            return "LOW_RISK: Consider using smaller model (llama-3.1-8b) to reduce costs"
        elif risk_score > 0.7:
            return "HIGH_RISK: Keep full model (llama-3.3-70b) for maximum reasoning depth"
        else:
            return "MEDIUM_RISK: Current model tier appropriate"


selfcheck_agent = SelfCheckAgent()
