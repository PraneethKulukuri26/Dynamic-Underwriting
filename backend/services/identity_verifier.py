"""
Identity Verifier Service
Integrates with Digiverifier for Aadhaar, PAN, GST, and UAN verification.
Currently uses mock responses mirroring actual API format.
"""

import logging
import hashlib
import random
from typing import Dict, Any, Optional, List
from backend.config import settings

logger = logging.getLogger(__name__)


class IdentityVerifier:
    """
    Verifies government-issued identities via Digiverifier APIs.
    Includes UAN cross-referencing for employment verification.
    """

    def __init__(self):
        self.base_url = settings.digiverifier_base_url
        self.api_key = settings.digiverifier_api_key
        self.use_mock = settings.use_mock_data or not self.api_key

    async def verify_pan(self, pan_number: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Verify PAN card number and optionally match against name."""
        if self.use_mock:
            return self._mock_pan_verification(pan_number, full_name)

        # Real API integration placeholder
        raise NotImplementedError("Production Digiverifier integration pending API key")

    async def verify_aadhaar(self, aadhaar_number: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """Verify Aadhaar number (uses OTP-based verification flow)."""
        if self.use_mock:
            return self._mock_aadhaar_verification(aadhaar_number, full_name)

        raise NotImplementedError("Production Digiverifier integration pending API key")

    async def verify_uan(self, uan_number: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify UAN (Universal Account Number) to check employment history.
        Primary defense against employment fraud per AIDUS spec.
        """
        if self.use_mock:
            return self._mock_uan_verification(uan_number, full_name)

        raise NotImplementedError("Production Digiverifier integration pending API key")

    async def verify_all(
        self,
        pan_number: Optional[str] = None,
        aadhaar_number: Optional[str] = None,
        uan_number: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run all available identity verifications."""
        results = {
            "pan_verified": None,
            "aadhaar_verified": None,
            "uan_verified": None,
            "name_match_score": None,
            "employment_history": None,
            "verification_details": {},
        }

        if pan_number:
            pan_result = await self.verify_pan(pan_number, full_name)
            results["pan_verified"] = pan_result.get("verified", False)
            results["verification_details"]["pan"] = pan_result

        if aadhaar_number:
            aadhaar_result = await self.verify_aadhaar(aadhaar_number, full_name)
            results["aadhaar_verified"] = aadhaar_result.get("verified", False)
            results["verification_details"]["aadhaar"] = aadhaar_result

        if uan_number:
            uan_result = await self.verify_uan(uan_number, full_name)
            results["uan_verified"] = uan_result.get("verified", False)
            results["employment_history"] = uan_result.get("employment_history", [])
            results["verification_details"]["uan"] = uan_result

        # Calculate name match score across verified documents
        name_scores = []
        for key in ["pan", "aadhaar", "uan"]:
            detail = results["verification_details"].get(key, {})
            if detail.get("name_match_score") is not None:
                name_scores.append(detail["name_match_score"])

        if name_scores:
            results["name_match_score"] = round(sum(name_scores) / len(name_scores), 4)

        return results

    # ---- Mock Implementations ----

    def _mock_pan_verification(self, pan: str, name: Optional[str]) -> dict:
        rng = random.Random(hash(pan))
        name_on_pan = name or "MOCK NAME"
        name_score = rng.uniform(0.75, 1.0) if name else None

        return {
            "verified": True,
            "pan_number": pan[:5] + "****" + pan[-1:],  # Masked
            "name_on_record": name_on_pan.upper(),
            "name_match_score": round(name_score, 4) if name_score else None,
            "pan_status": "ACTIVE",
            "pan_type": "Individual",
            "last_updated": "2024-01-15",
        }

    def _mock_aadhaar_verification(self, aadhaar: str, name: Optional[str]) -> dict:
        rng = random.Random(hash(aadhaar))
        return {
            "verified": True,
            "aadhaar_last_four": aadhaar[-4:],
            "name_match_score": round(rng.uniform(0.80, 1.0), 4) if name else None,
            "state": rng.choice(["Karnataka", "Maharashtra", "Tamil Nadu", "Delhi", "Telangana"]),
            "gender": rng.choice(["M", "F"]),
            "age_band": rng.choice(["18-25", "25-35", "35-45", "45-60"]),
        }

    def _mock_uan_verification(self, uan: str, name: Optional[str]) -> dict:
        rng = random.Random(hash(uan))

        employers = [
            {"name": "Infosys Limited", "from": "2019-06", "to": "2021-08", "designation": "Software Engineer"},
            {"name": "Wipro Technologies", "from": "2021-09", "to": "2023-05", "designation": "Senior Developer"},
            {"name": "TCS Digital", "from": "2023-06", "to": "present", "designation": "Lead Engineer"},
        ]

        num_employers = rng.randint(1, len(employers))
        selected = employers[:num_employers]

        return {
            "verified": True,
            "uan_number": uan[:4] + "****" + uan[-4:],
            "name_match_score": round(rng.uniform(0.85, 1.0), 4) if name else None,
            "member_id": f"MH/{rng.randint(10000, 99999)}/{rng.randint(1000, 9999)}",
            "employment_history": selected,
            "total_employers": len(selected),
            "pf_balance_range": rng.choice(["0-1L", "1L-5L", "5L-10L", "10L+"]),
            "contribution_regular": rng.random() > 0.2,
        }


# Singleton
identity_verifier = IdentityVerifier()
