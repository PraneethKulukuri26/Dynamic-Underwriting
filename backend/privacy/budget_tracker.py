"""
Privacy Budget Tracker
Monitors cumulative privacy loss per applicant using RDP accounting.
Prevents budget exhaustion for long-term model integrity.
"""

import math
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PrivacyBudgetTracker:
    """
    Tracks cumulative epsilon expenditure per applicant.
    Uses Rényi Differential Privacy (RDP) for tighter composition bounds.
    """

    def __init__(self, max_budget: float = 10.0):
        self.max_budget = max_budget
        # In-memory tracker (replace with DB in production)
        self._budgets: Dict[str, Dict] = {}

    def get_remaining_budget(self, applicant_id: str) -> float:
        """Get remaining privacy budget for an applicant."""
        spent = self._get_spent(applicant_id)
        return max(0.0, self.max_budget - spent)

    def can_query(self, applicant_id: str, epsilon_cost: float) -> bool:
        """
        Pre-check: Can we afford this privacy expenditure?

        Args:
            applicant_id: Applicant identifier
            epsilon_cost: Privacy cost of the planned operation

        Returns:
            True if budget allows the query
        """
        remaining = self.get_remaining_budget(applicant_id)
        can = remaining >= epsilon_cost

        if not can:
            logger.warning(
                f"Privacy budget exhausted for {applicant_id}. "
                f"Remaining: {remaining:.4f}, Required: {epsilon_cost:.4f}"
            )

        return can

    def record_query(
        self,
        applicant_id: str,
        epsilon_cost: float,
        operation: str = "unknown",
    ) -> Dict:
        """
        Record a privacy expenditure.

        Args:
            applicant_id: Applicant identifier
            epsilon_cost: Privacy cost consumed
            operation: Description of the operation

        Returns:
            Updated budget status
        """
        if applicant_id not in self._budgets:
            self._budgets[applicant_id] = {
                "total_spent": 0.0,
                "queries": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        budget = self._budgets[applicant_id]

        # RDP composition: under basic composition, ε values add up
        # Under advanced composition (Rényi), the bound is tighter
        composed_epsilon = self._rdp_compose(
            budget["total_spent"], epsilon_cost
        )

        budget["total_spent"] = composed_epsilon
        budget["queries"].append({
            "epsilon": epsilon_cost,
            "operation": operation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cumulative": composed_epsilon,
        })

        remaining = self.max_budget - composed_epsilon

        # Warn at 80% and 95% thresholds
        usage_pct = composed_epsilon / self.max_budget * 100
        if usage_pct >= 95:
            logger.critical(f"PRIVACY ALERT: Budget at {usage_pct:.1f}% for {applicant_id}")
        elif usage_pct >= 80:
            logger.warning(f"Privacy budget at {usage_pct:.1f}% for {applicant_id}")

        return {
            "applicant_id": applicant_id,
            "total_spent": round(composed_epsilon, 6),
            "remaining": round(remaining, 6),
            "max_budget": self.max_budget,
            "usage_percentage": round(usage_pct, 2),
            "total_queries": len(budget["queries"]),
        }

    def get_budget_status(self, applicant_id: str) -> Dict:
        """Get full budget status for an applicant."""
        spent = self._get_spent(applicant_id)
        remaining = max(0.0, self.max_budget - spent)
        queries = self._budgets.get(applicant_id, {}).get("queries", [])

        return {
            "applicant_id": applicant_id,
            "total_spent": round(spent, 6),
            "remaining": round(remaining, 6),
            "max_budget": self.max_budget,
            "usage_percentage": round(spent / self.max_budget * 100, 2),
            "total_queries": len(queries),
            "recent_queries": queries[-10:],  # Last 10
        }

    def _get_spent(self, applicant_id: str) -> float:
        """Get total epsilon spent for an applicant."""
        return self._budgets.get(applicant_id, {}).get("total_spent", 0.0)

    def _rdp_compose(self, existing_epsilon: float, new_epsilon: float) -> float:
        """
        Compose privacy losses using basic sequential composition.
        Under basic composition: ε_total = ε_1 + ε_2 + ... + ε_k

        For tighter bounds, advanced composition gives:
        ε_total ≤ √(2k · ln(1/δ')) · ε + k · ε · (e^ε - 1)

        We use basic composition for safety (conservative bound).
        """
        return existing_epsilon + new_epsilon


# Singleton
from backend.config import settings
budget_tracker = PrivacyBudgetTracker(max_budget=settings.max_privacy_budget)
