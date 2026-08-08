"""
Balance Enrichment Engine
Reconstructs running balances from transaction history when banks don't provide them.
Implements transaction categorization using regex patterns.
"""

import re
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)

# Transaction categorization patterns
CATEGORY_PATTERNS = {
    "SALARY": [
        r"(?i)salary|payroll|wages|stipend|income|compensation",
        r"(?i)NEFT.*(?:salary|pay)|RTGS.*(?:salary|pay)",
    ],
    "RENT": [
        r"(?i)rent|lease|housing|apartment|flat\s+rent",
    ],
    "UTILITIES": [
        r"(?i)electric|water|gas|broadband|internet|wifi|telephone|phone\s+bill",
        r"(?i)(?:BSES|TATA\s+POWER|AIRTEL|JIO|VODAFONE)",
    ],
    "GROCERIES": [
        r"(?i)grocer|supermarket|bigbasket|blinkit|zepto|dmart|reliance\s+fresh",
    ],
    "TRANSPORT": [
        r"(?i)uber|ola|rapido|metro|petrol|diesel|fuel|parking",
        r"(?i)(?:IRCTC|makemytrip|cleartrip)",
    ],
    "FOOD_DELIVERY": [
        r"(?i)swiggy|zomato|dominos|pizza|restaurant|dining",
    ],
    "INSURANCE": [
        r"(?i)insurance|premium|LIC|HDFC\s+LIFE|ICICI\s+PRU",
    ],
    "LOAN_EMI": [
        r"(?i)EMI|loan|mortgage|instalment|repayment",
    ],
    "INVESTMENT": [
        r"(?i)mutual\s+fund|SIP|stock|demat|trading|zerodha|groww|upstox",
    ],
    "TRANSFER": [
        r"(?i)UPI|NEFT|RTGS|IMPS|transfer|payment",
    ],
    "ATM_WITHDRAWAL": [
        r"(?i)ATM|cash\s+withdrawal|WDL",
    ],
    "ENTERTAINMENT": [
        r"(?i)netflix|hotstar|spotify|amazon\s+prime|movie|gaming",
    ],
    "SHOPPING": [
        r"(?i)amazon|flipkart|myntra|ajio|shopping|purchase",
    ],
    "MEDICAL": [
        r"(?i)hospital|pharmacy|medical|doctor|clinic|health",
    ],
    "EDUCATION": [
        r"(?i)school|college|university|tuition|course|udemy|coursera",
    ],
}


class BalanceEnrichmentEngine:
    """
    Reconstructs running balances and categorizes transactions.
    Critical when financial institutions don't provide running balance data.
    """

    def categorize_transaction(self, description: str) -> str:
        """
        Categorize a transaction based on its description using regex patterns.

        Args:
            description: Transaction description text

        Returns:
            Category string or 'UNCATEGORIZED'
        """
        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, description):
                    return category
        return "UNCATEGORIZED"

    def reconstruct_running_balances(
        self,
        transactions: List[Dict],
        current_balance: Optional[float] = None,
    ) -> List[Dict]:
        """
        Reconstruct running balance history by replaying transactions chronologically.
        If current_balance is provided, works backwards from the current state.

        Args:
            transactions: List of transaction dicts with 'date', 'amount', 'type'
            current_balance: Known current balance to anchor calculations

        Returns:
            List of {date, balance, transaction_id} entries
        """
        if not transactions:
            return []

        # Sort chronologically (oldest first)
        sorted_txns = sorted(transactions, key=lambda t: t.get("date", ""))

        if current_balance is not None:
            # Work backwards from known balance
            return self._reconstruct_from_current(sorted_txns, current_balance)
        else:
            # Forward replay starting from 0 (relative balances)
            return self._reconstruct_forward(sorted_txns)

    def _reconstruct_from_current(
        self, sorted_txns: List[Dict], current_balance: float
    ) -> List[Dict]:
        """Reconstruct by working backwards from known current balance."""
        running_balances = []
        balance = current_balance

        # Process in reverse to work backwards
        for txn in reversed(sorted_txns):
            amount = txn.get("amount", 0)
            txn_type = txn.get("type", "DEBIT")

            running_balances.append({
                "date": txn.get("date"),
                "balance": round(balance, 2),
                "transaction_id": txn.get("transaction_id"),
            })

            # Reverse the transaction effect
            if txn_type == "CREDIT":
                balance -= amount
            else:
                balance += amount

        # Add the opening balance
        running_balances.append({
            "date": sorted_txns[0].get("date"),
            "balance": round(balance, 2),
            "transaction_id": "OPENING_BALANCE",
        })

        running_balances.reverse()
        return running_balances

    def _reconstruct_forward(self, sorted_txns: List[Dict]) -> List[Dict]:
        """Forward replay for relative balance tracking."""
        running_balances = []
        balance = 0.0

        for txn in sorted_txns:
            amount = txn.get("amount", 0)
            txn_type = txn.get("type", "DEBIT")

            if txn_type == "CREDIT":
                balance += amount
            else:
                balance -= amount

            running_balances.append({
                "date": txn.get("date"),
                "balance": round(balance, 2),
                "transaction_id": txn.get("transaction_id"),
            })

        return running_balances

    def analyze_financial_health(
        self, transactions: List[Dict]
    ) -> Dict:
        """
        Compute aggregated financial health metrics from transaction history.

        Returns:
            Dict with income regularity, expense breakdown, savings rate, etc.
        """
        total_credits = 0.0
        total_debits = 0.0
        salary_amounts = []
        category_totals = {}

        for txn in transactions:
            amount = txn.get("amount", 0)
            txn_type = txn.get("type", "DEBIT")
            description = txn.get("description", "")
            category = txn.get("category") or self.categorize_transaction(description)

            if txn_type == "CREDIT":
                total_credits += amount
                if category == "SALARY":
                    salary_amounts.append(amount)
            else:
                total_debits += amount

            category_totals[category] = category_totals.get(category, 0) + amount

        # Income regularity: coefficient of variation of salary amounts
        income_regularity = 0.0
        avg_income = 0.0
        if salary_amounts:
            avg_income = sum(salary_amounts) / len(salary_amounts)
            if avg_income > 0:
                variance = sum((s - avg_income) ** 2 for s in salary_amounts) / len(salary_amounts)
                std_dev = variance ** 0.5
                cv = std_dev / avg_income
                income_regularity = max(0.0, 1.0 - cv)  # Lower CV = more regular

        return {
            "total_credits_30d": round(total_credits, 2),
            "total_debits_30d": round(total_debits, 2),
            "avg_monthly_income": round(avg_income, 2),
            "income_regularity_score": round(income_regularity, 4),
            "transaction_categories": category_totals,
            "transaction_count_30d": len(transactions),
            "savings_rate": round((total_credits - total_debits) / max(total_credits, 1), 4),
        }


# Singleton
balance_enrichment = BalanceEnrichmentEngine()
