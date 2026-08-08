"""
OSINT Correlation Engine
Bridges disparate intelligence signals into a unified Trust Score.
Implements the 4-step correlation logic from the AIDUS spec.
"""

import logging
from typing import Optional, Dict, Any
from backend.services.sherlock_runner import sherlock_runner
from backend.services.breach_checker import breach_checker
from backend.services.identity_verifier import identity_verifier

logger = logging.getLogger(__name__)

# Trust score dimension weights
WEIGHTS = {
    "network_depth": 0.20,
    "footprint_longevity": 0.25,
    "professional_consistency": 0.30,
    "identity_verification": 0.25,
}


class CorrelationEngine:
    """
    Cross-references OSINT signals to compute a composite Trust Score.
    Implements the 4-step Correlation Engine Logic:
      1. Seed Input → 2. Platform Mapping → 3. Breach History → 4. Professional Synthesis
    """

    async def correlate(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        username: Optional[str] = None,
        pan_number: Optional[str] = None,
        aadhaar_number: Optional[str] = None,
        uan_number: Optional[str] = None,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full correlation pipeline.

        Args:
            Primary identifiers (email, phone, username) and verification IDs

        Returns:
            Composite trust score with per-dimension breakdown
        """
        results = {
            "network_depth_score": 0.0,
            "footprint_longevity_score": 0.0,
            "professional_consistency_score": 0.0,
            "identity_verification_score": 0.0,
            "overall_trust_score": 0.0,
            "platform_matches": [],
            "breach_data": {},
            "identity_data": {},
            "risk_flags": [],
        }

        # Step 1: Seed Input — start with whatever identifiers we have
        logger.info(f"Correlation engine starting with seeds: email={bool(email)}, username={bool(username)}")

        # Step 2: Platform Mapping via Sherlock
        if username:
            sherlock_result = await sherlock_runner.search_username(username, resume_keywords=full_name or "")
            results["platform_matches"] = sherlock_result.get("platforms", [])
            results["network_depth_score"] = self._calculate_network_depth(sherlock_result)
        else:
            results["risk_flags"].append("NO_USERNAME_PROVIDED")

        # Step 3: Breach History via HIBP & Email Intelligence
        if email:
            breach_result = await breach_checker.check_email(email)
            results["breach_data"] = breach_result
            longevity_years = breach_result.get("footprint_longevity_years", 0)
            results["footprint_longevity_score"] = breach_checker.calculate_longevity_score(longevity_years)
            
            # New: Email Intelligence (Gravatar & Holehe)
            from backend.services.email_intelligence import email_intelligence
            email_intel = await email_intelligence.analyze_email(email)
            results["breach_data"]["gravatar"] = email_intel.get("gravatar")
            results["breach_data"]["registered_platforms"] = email_intel.get("registered_platforms", [])

            # Flag: Identity too new (no breach history)
            if breach_result.get("total_breaches", 0) == 0:
                results["risk_flags"].append("NO_BREACH_HISTORY_IDENTITY_MAY_BE_NEW")
        else:
            results["risk_flags"].append("NO_EMAIL_PROVIDED")

        # Step 4: Professional Synthesis — cross-reference with gov IDs
        identity_result = await identity_verifier.verify_all(
            pan_number=pan_number,
            aadhaar_number=aadhaar_number,
            uan_number=uan_number,
            full_name=full_name,
        )
        results["identity_data"] = identity_result

        # Calculate professional consistency
        results["professional_consistency_score"] = self._calculate_professional_consistency(
            results["platform_matches"], identity_result
        )

        # Calculate identity verification score
        results["identity_verification_score"] = self._calculate_identity_score(identity_result)

        # Compute weighted overall trust score
        results["overall_trust_score"] = round(
            results["network_depth_score"] * WEIGHTS["network_depth"]
            + results["footprint_longevity_score"] * WEIGHTS["footprint_longevity"]
            + results["professional_consistency_score"] * WEIGHTS["professional_consistency"]
            + results["identity_verification_score"] * WEIGHTS["identity_verification"],
            4
        )

        # Flag: Overall trust too low
        if results["overall_trust_score"] < 0.3:
            results["risk_flags"].append("LOW_OVERALL_TRUST_SCORE")

        logger.info(f"Correlation complete. Trust score: {results['overall_trust_score']}")
        return results

    def _calculate_network_depth(self, sherlock_result: Dict) -> float:
        """
        Score based on how many platforms the username was found on.
        More platforms = deeper network = more verifiable identity.
        """
        found = sherlock_result.get("total_found", 0)
        checked = sherlock_result.get("total_checked", 1)

        # Check for professional platforms specifically
        platforms = sherlock_result.get("platforms", [])
        has_professional = any(p.get("category") == "PROFESSIONAL" for p in platforms)
        has_social = any(p.get("category") == "SOCIAL" for p in platforms)

        base_score = min(found / 15.0, 1.0)  # Cap at 15 platforms

        # Bonus for having both professional and social
        if has_professional and has_social:
            base_score = min(base_score + 0.1, 1.0)

        return round(base_score, 4)

    def _calculate_professional_consistency(
        self, platform_matches: list, identity_data: Dict
    ) -> float:
        """
        Cross-reference professional platforms with UAN employment data.
        Higher score when LinkedIn/GitHub match employment history.
        """
        score = 0.5  # Base score

        # Check if LinkedIn or professional platforms found
        professional_platforms = [p for p in platform_matches if p.get("category") == "PROFESSIONAL"]
        if professional_platforms:
            score += 0.15

        # UAN employment history adds significant credibility
        employment = identity_data.get("employment_history", [])
        if employment:
            score += 0.15
            # Regular PF contributions = stable employment
            uan_details = identity_data.get("verification_details", {}).get("uan", {})
            if uan_details.get("contribution_regular"):
                score += 0.1

        # Name match across documents
        name_match = identity_data.get("name_match_score")
        if name_match is not None:
            if name_match >= 0.9:
                score += 0.1
            elif name_match < 0.7:
                score -= 0.2

        return round(min(max(score, 0.0), 1.0), 4)

    def _calculate_identity_score(self, identity_data: Dict) -> float:
        """Score based on government ID verification results."""
        score = 0.0
        verifications = 0

        if identity_data.get("pan_verified"):
            score += 0.35
            verifications += 1
        if identity_data.get("aadhaar_verified"):
            score += 0.35
            verifications += 1
        if identity_data.get("uan_verified"):
            score += 0.30
            verifications += 1

        if verifications == 0:
            return 0.1  # No verifications possible

        return round(score, 4)


# Singleton
correlation_engine = CorrelationEngine()
