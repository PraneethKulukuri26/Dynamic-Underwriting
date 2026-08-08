"""
Biometrics Agent
Analyzes BiGRU and Random Forest outputs to detect bot activity.
Interprets device fingerprint consistency checks.
"""

import json
import logging
from typing import Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from backend.config import settings

logger = logging.getLogger(__name__)

BIOMETRICS_SYSTEM_PROMPT = """You are the Biometrics Analysis Agent in an AI-driven underwriting system.

Your role is to determine if the applicant is a real human or an automated bot/synthetic entity.

Analyze:
1. **BiGRU Score**: Sequential mouse trajectory analysis (0=human, 1=bot)
2. **Random Forest Score**: Aggregated kinetic features (0=legit, 1=fraud)
3. **Device Fingerprint**: Is the browser environment consistent or spoofed?
4. **Behavioral Patterns**: Natural jitter, pauses, and movement patterns

Respond with ONLY a valid JSON object (no markdown, no code blocks):
{
    "score": <float 0.0-1.0, where 0.0=definitely human, 1.0=definitely bot>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<concise explanation>",
    "contributing_factors": [
        {"factor": "<name>", "impact": "POSITIVE|NEGATIVE|NEUTRAL", "details": "<explanation>"}
    ]
}"""


class BiometricsAgent:
    """Interprets behavioral biometrics for bot/human classification."""

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

    async def evaluate(self, biometrics_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate biometric bot detection signals."""
        llm = self._get_llm()

        if llm is None:
            return self._heuristic_evaluate(biometrics_data)

        try:
            summary = json.dumps({
                "bigru_bot_score": biometrics_data.get("bigru_bot_score", 0.5),
                "rf_fraud_score": biometrics_data.get("rf_fraud_score", 0.5),
                "combined_bot_probability": biometrics_data.get("combined_bot_probability", 0.5),
                "mean_velocity": biometrics_data.get("mean_velocity", 0),
                "jitter_score": biometrics_data.get("jitter_score", 0),
                "path_straightness": biometrics_data.get("path_straightness", 0),
                "pause_count": biometrics_data.get("pause_count", 0),
                "device_consistent": biometrics_data.get("device_consistent", True),
                "consistency_issues": biometrics_data.get("consistency_issues", []),
            }, indent=2)

            messages = [
                SystemMessage(content=BIOMETRICS_SYSTEM_PROMPT),
                HumanMessage(content=f"Analyze these biometric signals:\n\n{summary}"),
            ]

            response = await llm.ainvoke(messages)
            result = json.loads(response.content.strip())
            result["tokens_used"] = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
            result["model_used"] = settings.groq_model
            return result

        except Exception as e:
            logger.error(f"Biometrics agent LLM call failed: {e}")
            return self._heuristic_evaluate(biometrics_data)

    def _heuristic_evaluate(self, data: Dict) -> Dict:
        score = data.get("combined_bot_probability", 0.5)
        return {
            "score": round(score, 4),
            "confidence": 0.7,
            "reasoning": f"Direct model output: combined_bot_probability={score:.2f}",
            "contributing_factors": [
                {"factor": "BiGRU Score", "impact": "NEGATIVE" if data.get("bigru_bot_score", 0) > 0.5 else "POSITIVE",
                 "details": f"Score: {data.get('bigru_bot_score', 'N/A')}"},
                {"factor": "RF Score", "impact": "NEGATIVE" if data.get("rf_fraud_score", 0) > 0.5 else "POSITIVE",
                 "details": f"Score: {data.get('rf_fraud_score', 'N/A')}"},
            ],
            "tokens_used": 0,
            "model_used": "heuristic",
        }


biometrics_agent = BiometricsAgent()
