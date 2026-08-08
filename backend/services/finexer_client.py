"""
Finexer Open Finance API Client
Handles consent-first bank account access, transaction retrieval, and balance enrichment.
Supports mock mode for development without real API keys.
"""

import httpx
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import json
from langchain_groq import ChatGroq
from backend.config import settings

logger = logging.getLogger(__name__)


class FinexerClient:
    """
    Client for Finexer Open Finance APIs.
    Implements tokenized, credential-free bank account access.
    """

    def __init__(self):
        self.base_url = settings.finexer_base_url
        self.api_key = settings.finexer_api_key
        self.callback_url = settings.finexer_callback_url
        self.use_mock = settings.use_mock_data or not self.api_key
        self._mock_data_store = {}

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AIDUS-Backend/1.0",
        }

    async def initiate_consent(
        self,
        applicant_id: str,
        scopes: List[str],
        bank_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a consent authorization URL for the applicant.
        The user will be redirected to their bank for SCA.
        """
        if self.use_mock:
            return self._mock_initiate_consent(applicant_id, scopes)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/consents",
                headers=self._get_headers(),
                json={
                    "applicant_id": applicant_id,
                    "scopes": scopes,
                    "callback_url": self.callback_url,
                    "bank_id": bank_id,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def exchange_auth_code(self, code: str, consent_token_id: str) -> Dict[str, Any]:
        """
        Exchange the OAuth authorization code for access/refresh tokens.
        Called after the bank redirects back with the code.
        """
        if self.use_mock:
            return self._mock_exchange_code(consent_token_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/token",
                headers=self._get_headers(),
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.callback_url,
                },
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_accounts(self, access_token: str) -> List[Dict[str, Any]]:
        """Retrieve linked bank accounts using AIS endpoints."""
        if self.use_mock:
            return self._mock_accounts()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/accounts",
                headers={**self._get_headers(), "Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json().get("accounts", [])

    async def get_transactions(
        self,
        access_token: str,
        account_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve transaction history for an account."""
        if self.use_mock:
            if access_token in self._mock_data_store:
                return self._mock_data_store[access_token]
            return self._mock_transactions()

        params = {"account_id": account_id}
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/accounts/{account_id}/transactions",
                headers={**self._get_headers(), "Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json().get("transactions", [])

    async def get_balances(self, access_token: str, account_id: str) -> Dict[str, Any]:
        """Retrieve current and available balances for an account."""
        if self.use_mock:
            return self._mock_balances()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/accounts/{account_id}/balances",
                headers={**self._get_headers(), "Authorization": f"Bearer {access_token}"},
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    # ---- Mock Data Generators ----

    def _mock_initiate_consent(self, applicant_id: str, scopes: List[str]) -> dict:
        # We don't generate a token ID here because the consent router generates the ConsentToken ID
        # and we need to pass THAT id in the state. Wait, the ConsentInitiateResponse in consent.py handles it!
        # Actually consent_manager creates ConsentToken then calls finexer_client.initiate_consent, which is wrong,
        # consent_manager passes bank_id, but doesn't pass consent_token_id!
        # Wait, consent_manager calls `initiate_consent` first, then updates `authorization_url`!
        # So we can just return a generic URL and the consent_manager will append state=xxx or something?
        # Let's check consent_manager.py to see how authorization_url is used.
        return {
            "consent_id": "mock",
            "authorization_url": "mock_bank.html",
            "scopes": scopes,
            "expires_in": 300,
        }

    async def mock_authorize(self, consent_token_id: uuid.UUID, income: float, name: str):
        """Simulate OAuth authorization and trigger LLM to generate bank data."""
        if not settings.groq_api_key:
            logger.warning("No Groq API key found. Falling back to random mock transactions.")
            return

        try:
            llm = ChatGroq(
                model=settings.groq_model,
                temperature=0.7,
                api_key=settings.groq_api_key,
            )
            
            prompt = f"""You are a financial data synthesizer for a mock banking API. 
Generate exactly 30 realistic, messy bank transactions spanning the last 30 days for a user named '{name}' with a declared monthly income of INR {income}.
The output MUST be a valid JSON array of objects. Do not include markdown code blocks (e.g. ```json). Output raw JSON only.

Each object must have the following keys:
- "transaction_id": unique string (e.g. "TXN001")
- "date": ISO format date string (e.g. "2023-10-15T14:30:00Z")
- "amount": positive float representing absolute amount
- "currency": "INR"
- "type": "CREDIT" or "DEBIT"
- "description": messy, realistic merchant description (e.g. "UPI/ZOMATO/XYZ123", "NEFT-SALARY-OCT")

Ensure the total monthly salary credits roughly match {income}. Include typical expenses: groceries, rent, utilities, entertainment, transfers. 
Make the descriptions realistic for the Indian banking context (e.g. UPI, NEFT, IMPS).
"""
            messages = [{"role": "system", "content": prompt}]
            response = await llm.ainvoke(messages)
            
            content = response.content.strip()
            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            
            transactions = json.loads(content)
            access_token = f"mock_access_{consent_token_id.hex}"
            self._mock_data_store[access_token] = transactions
            logger.info(f"Successfully generated {len(transactions)} AI transactions for {name}.")
            
        except Exception as e:
            logger.error(f"Failed to generate LLM transactions: {e}")
            # Will fallback to random mock transactions if cache miss

    def _mock_exchange_code(self, consent_token_id: str) -> dict:
        return {
            "access_token": f"mock_access_{uuid.uuid4().hex[:16]}",
            "refresh_token": f"mock_refresh_{uuid.uuid4().hex[:16]}",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "accounts balances transactions",
        }

    def _mock_accounts(self) -> List[dict]:
        return [
            {
                "account_id": "ACC001",
                "bank_name": "State Bank of India",
                "account_type": "SAVINGS",
                "currency": "INR",
                "iban": "IN00SBIN0001234567890",
            },
            {
                "account_id": "ACC002",
                "bank_name": "HDFC Bank",
                "account_type": "CURRENT",
                "currency": "INR",
                "iban": "IN00HDFC0009876543210",
            },
        ]

    def _mock_transactions(self, income: float = 50000.0) -> List[dict]:
        now = datetime.now(timezone.utc)
        transactions = []
        import random
        
        # Scale factor based on declared income (baseline 50000)
        scale = max(0.1, income / 50000.0)

        categories = {
            "SALARY": (50000 * scale, 75000 * scale),
            "RENT": (-15000 * scale, -12000 * scale),
            "UTILITIES": (-3000 * scale, -1500 * scale),
            "GROCERIES": (-5000 * scale, -2000 * scale),
            "TRANSPORT": (-3000 * scale, -1000 * scale),
            "ENTERTAINMENT": (-2000 * scale, -500 * scale),
            "TRANSFER_IN": (5000 * scale, 20000 * scale),
            "TRANSFER_OUT": (-10000 * scale, -3000 * scale),
        }

        for i in range(30):
            date = now - timedelta(days=i)
            # 1-3 transactions per day
            for j in range(random.randint(1, 3)):
                cat = random.choice(list(categories.keys()))
                low, high = categories[cat]
                amount = round(random.uniform(low, high), 2)
                transactions.append({
                    "transaction_id": f"TXN{i:03d}{j}",
                    "date": date.isoformat(),
                    "amount": abs(amount),
                    "currency": "INR",
                    "type": "CREDIT" if amount > 0 else "DEBIT",
                    "description": f"Mock {cat.replace('_', ' ').title()} Transaction",
                    "category": cat,
                    "merchant": f"MOCK_{cat}_MERCHANT",
                })

        return transactions

    def _mock_balances(self, income: float = 50000.0) -> dict:
        scale = max(0.1, income / 50000.0)
        return {
            "current_balance": 245000.50 * scale,
            "available_balance": 240000.00 * scale,
            "currency": "INR",
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
finexer_client = FinexerClient()
