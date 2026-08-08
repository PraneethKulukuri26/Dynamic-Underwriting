"""
OSINT Agent
Validates professional history and UAN-verified employment signals.
Interprets correlation engine outputs for risk assessment.
"""

import json
import logging
from typing import Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from backend.config import settings

logger = logging.getLogger(__name__)

OSINT_SYSTEM_PROMPT = """You are the OSINT Verification Agent in an AI-driven underwriting system.

Your role is to assess an applicant's identity authenticity based on open-source intelligence signals.

Analyze the following dimensions:
1. **Network Depth**: How many platforms is the identity present on? (More = more verifiable)
2. **Footprint Longevity**: How old is the digital footprint? (Older = more trustworthy)
3. **Professional Consistency**: Does LinkedIn/GitHub match declared employment and UAN records?
4. **Synthetic Identity Risk**: Are there signs this is a fabricated identity?

A "clean" identity with no breach history, created days ago, is MORE suspicious than one with a 5-year breach trail.

Respond with ONLY a valid JSON object (no markdown, no code blocks):
{
    "score": <float 0.0-1.0, where 0.0=fully verified, 1.0=likely synthetic>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<concise explanation>",
    "contributing_factors": [
        {"factor": "<name>", "impact": "POSITIVE|NEGATIVE|NEUTRAL", "details": "<explanation>"}
    ]
}"""


class OSINTAgent:
    """Interprets OSINT pipeline results for identity risk assessment."""

    def __init__(self):
        self.llm = None

    def _get_llm(self):
        if self.llm is None and settings.groq_api_key:
            self.llm = ChatGroq(
                model=settings.groq_model,
                temperature=settings.groq_temperature,
                max_tokens=settings.groq_max_tokens,
                api_key=settings.groq_api_key,
            )
        return self.llm

    async def evaluate(self, osint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate OSINT correlation results."""
        llm = self._get_llm()

        # Deterministic Routing for Cost Optimization
        network_depth = osint_data.get("network_depth_score", 0)
        id_verified = osint_data.get("identity_data", {}).get("pan_verified", False)
        platforms_found = len(osint_data.get("platform_matches", []))
        
        # Fast path rejection
        if network_depth == 0 and not id_verified:
            logger.info("Fast path routed (REJECTION): Zero network depth and failed ID.")
            return self._heuristic_evaluate(osint_data)
            
        # Fast path approval (requires high confidence metrics)
        consistency = osint_data.get("professional_consistency_score", 0)
        # Note: Bureau score isn't in osint_data, but we have platforms and consistency
        if platforms_found > 3 and consistency >= 0.8 and id_verified:
            logger.info("Fast path routed (APPROVAL): High footprint density and consistency.")
            return self._heuristic_evaluate(osint_data)

        if llm is None:
            return self._heuristic_evaluate(osint_data)

        try:
            summary = json.dumps({
                "trust_score": osint_data.get("overall_trust_score", 0),
                "network_depth": osint_data.get("network_depth_score", 0),
                "footprint_longevity": osint_data.get("footprint_longevity_score", 0),
                "professional_consistency": osint_data.get("professional_consistency_score", 0),
                "identity_verification": osint_data.get("identity_verification_score", 0),
                "platforms_found": len(osint_data.get("platform_matches", [])),
                "breaches_found": osint_data.get("breach_data", {}).get("total_breaches", 0),
                "longevity_years": osint_data.get("breach_data", {}).get("footprint_longevity_years", 0),
                "identity_verified": osint_data.get("identity_data", {}).get("pan_verified", False),
                "risk_flags": osint_data.get("risk_flags", []),
            }, indent=2)

            messages = [
                SystemMessage(content=OSINT_SYSTEM_PROMPT),
                HumanMessage(content=f"Analyze this OSINT intelligence:\n\n{summary}"),
            ]

            response = await llm.ainvoke(messages)
            result = json.loads(response.content.strip())
            result["tokens_used"] = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
            result["model_used"] = settings.groq_model
            return result

        except Exception as e:
            logger.error(f"OSINT agent LLM call failed: {e}")
            return self._heuristic_evaluate(osint_data)

    def _heuristic_evaluate(self, data: Dict) -> Dict:
        trust = data.get("overall_trust_score", 0.5)
        # Invert trust score to get risk (higher trust = lower risk)
        score = max(0.0, min(1.0, 1.0 - trust))

        return {
            "score": round(score, 4),
            "confidence": 0.5,
            "reasoning": f"Heuristic: trust_score={trust:.2f}, risk={score:.2f}",
            "contributing_factors": [
                {"factor": "Trust Score", "impact": "POSITIVE" if trust > 0.6 else "NEGATIVE",
                 "details": f"Overall trust: {trust:.2f}"}
            ],
            "tokens_used": 0,
            "model_used": "heuristic",
        }


osint_agent = OSINTAgent()
