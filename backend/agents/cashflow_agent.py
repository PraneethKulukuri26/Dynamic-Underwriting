"""
Cash-Flow Agent
Evaluates Finexer-derived transaction patterns, running balances, and income consistency.
"""

import json
import logging
from typing import Dict, Any
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from backend.config import settings

logger = logging.getLogger(__name__)

CASHFLOW_SYSTEM_PROMPT = """You are the Cash-Flow Analysis Agent in an AI-driven underwriting system.

Your role is to evaluate an applicant's financial health based on their bank transaction data.

Analyze the following dimensions and provide a risk score (0.0 = low risk, 1.0 = high risk):

1. **Income Consistency**: Is the salary/income regular? Are amounts consistent?
2. **Expense-to-Income Ratio**: What percentage of income is spent?
3. **Balance Trends**: Is the balance trending upward (savings) or downward (depletion)?
4. **Transaction Anomalies**: Any unusual large transactions, new payees, or irregular patterns?
5. **Savings Capacity**: Can the applicant service new debt?

Respond with ONLY a valid JSON object (no markdown, no code blocks):
{
    "score": <float 0.0-1.0, where 0.0=low risk>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<concise explanation>",
    "contributing_factors": [
        {"factor": "<name>", "impact": "POSITIVE|NEGATIVE|NEUTRAL", "details": "<explanation>"}
    ]
}"""


class CashFlowAgent:
    """Evaluates financial data for creditworthiness signals."""

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

    async def evaluate(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate financial data and produce a cash flow risk score.

        Args:
            financial_data: Aggregated financial profile from Finexer

        Returns:
            Agent output with score, confidence, reasoning, and factors
        """
        llm = self._get_llm()

        if llm is None:
            return self._heuristic_evaluate(financial_data)

        try:
            # Prepare financial summary for the LLM
            summary = self._prepare_summary(financial_data)

            messages = [
                SystemMessage(content=CASHFLOW_SYSTEM_PROMPT),
                HumanMessage(content=f"Analyze this applicant's financial data:\n\n{summary}"),
            ]

            response = await llm.ainvoke(messages)

            # Parse JSON response
            result = json.loads(response.content.strip())
            result["tokens_used"] = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)
            result["model_used"] = settings.groq_model

            return result

        except Exception as e:
            logger.error(f"CashFlow agent LLM call failed: {e}")
            return self._heuristic_evaluate(financial_data)

    def _prepare_summary(self, data: Dict) -> str:
        """Format financial data into a readable summary for the LLM."""
        return json.dumps({
            "avg_monthly_income": data.get("avg_monthly_income", 0),
            "income_regularity_score": data.get("income_regularity_score", 0),
            "total_credits_30d": data.get("total_credits_30d", 0),
            "total_debits_30d": data.get("total_debits_30d", 0),
            "savings_rate": data.get("savings_rate", 0),
            "transaction_count_30d": data.get("transaction_count_30d", 0),
            "top_expense_categories": data.get("transaction_categories", {}),
            "current_balance": data.get("current_balance", 0),
        }, indent=2)

    def _heuristic_evaluate(self, data: Dict) -> Dict:
        """Fallback heuristic when LLM is unavailable."""
        income = data.get("avg_monthly_income", 0)
        regularity = data.get("income_regularity_score", 0)
        savings_rate = data.get("savings_rate", 0)

        # Simple heuristic scoring
        score = 0.5  # Start neutral

        if regularity > 0.8:
            score -= 0.15
        elif regularity < 0.4:
            score += 0.15

        if savings_rate > 0.2:
            score -= 0.15
        elif savings_rate < 0:
            score += 0.2

        if income > 50000:
            score -= 0.1
        elif income < 15000:
            score += 0.1

        score = max(0.0, min(1.0, score))

        factors = []
        if regularity > 0.8:
            factors.append({"factor": "Income Regularity", "impact": "POSITIVE", "details": f"Score: {regularity:.2f}"})
        if savings_rate > 0.2:
            factors.append({"factor": "Savings Rate", "impact": "POSITIVE", "details": f"{savings_rate:.1%}"})
        if savings_rate < 0:
            factors.append({"factor": "Negative Savings", "impact": "NEGATIVE", "details": "Spending exceeds income"})

        return {
            "score": round(score, 4),
            "confidence": 0.6,
            "reasoning": f"Heuristic evaluation: income={income}, regularity={regularity:.2f}, savings_rate={savings_rate:.2f}",
            "contributing_factors": factors,
            "tokens_used": 0,
            "model_used": "heuristic",
        }


# Singleton
cashflow_agent = CashFlowAgent()
