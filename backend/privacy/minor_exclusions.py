"""
Minor Exclusions Filter
Prevents the model from using protected characteristics as proxy signals.
Implements GDPR Article 9 and Indian DPDP Act protections.
"""

import logging
from typing import Dict, Any, List, Set, Tuple

logger = logging.getLogger(__name__)

# Protected fields that must NEVER be used in risk scoring
PROTECTED_FIELDS: Set[str] = {
    # Age-related
    "age", "date_of_birth", "dob", "birth_date", "birth_year", "age_band",
    # Gender/Sex
    "sex", "gender", "gender_identity", "sexual_orientation",
    # Caste (India-specific)
    "caste", "caste_category", "caste_certificate", "sc", "st", "obc", "general",
    # Religion
    "religion", "religious_affiliation", "faith",
    # Race/Ethnicity
    "race", "ethnicity", "ethnic_group", "nationality_origin",
    # Disability
    "disability", "disability_status", "handicap", "pwd",
    # Marital status
    "marital_status", "married", "single", "divorced",
    # Genetic/Biometric (non-behavioral)
    "genetic_data", "blood_type", "dna",
}

# Protected value patterns (regex-free check for values)
PROTECTED_VALUE_KEYWORDS = {
    "hindu", "muslim", "christian", "sikh", "buddhist", "jain",
    "scheduled caste", "scheduled tribe", "other backward",
    "male", "female", "transgender", "non-binary",
}


class MinorExclusionFilter:
    """
    Filters out protected characteristics from data before risk scoring.
    Ensures model fairness by preventing proxy discrimination.
    """

    def __init__(
        self,
        protected_fields: Set[str] = None,
        protected_values: Set[str] = None,
    ):
        self.protected_fields = protected_fields or PROTECTED_FIELDS
        self.protected_values = protected_values or PROTECTED_VALUE_KEYWORDS

    def filter_dict(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict]]:
        """
        Remove protected fields from a data dictionary.

        Args:
            data: Input dictionary potentially containing protected characteristics

        Returns:
            Tuple of (filtered_dict, list of excluded fields with audit info)
        """
        filtered = {}
        exclusions = []

        for key, value in data.items():
            key_lower = key.lower().strip()

            if key_lower in self.protected_fields:
                exclusions.append({
                    "field": key,
                    "reason": "PROTECTED_CHARACTERISTIC",
                    "category": self._categorize_field(key_lower),
                })
                continue

            # Recursively filter nested dicts
            if isinstance(value, dict):
                sub_filtered, sub_exclusions = self.filter_dict(value)
                filtered[key] = sub_filtered
                exclusions.extend(sub_exclusions)
            elif isinstance(value, list):
                filtered_list = []
                for item in value:
                    if isinstance(item, dict):
                        sub_filtered, sub_exclusions = self.filter_dict(item)
                        filtered_list.append(sub_filtered)
                        exclusions.extend(sub_exclusions)
                    else:
                        filtered_list.append(item)
                filtered[key] = filtered_list
            else:
                filtered[key] = value

        if exclusions:
            logger.info(f"Minor exclusion filter removed {len(exclusions)} protected fields")

        return filtered, exclusions

    def scan_for_protected(self, data: Dict[str, Any]) -> List[Dict]:
        """Scan data for protected characteristics without removing them."""
        _, exclusions = self.filter_dict(data)
        return exclusions

    def _categorize_field(self, field: str) -> str:
        """Categorize the protected field type."""
        age_fields = {"age", "date_of_birth", "dob", "birth_date", "birth_year", "age_band"}
        gender_fields = {"sex", "gender", "gender_identity", "sexual_orientation"}
        caste_fields = {"caste", "caste_category", "caste_certificate", "sc", "st", "obc"}
        religion_fields = {"religion", "religious_affiliation", "faith"}

        if field in age_fields:
            return "AGE"
        elif field in gender_fields:
            return "GENDER"
        elif field in caste_fields:
            return "CASTE"
        elif field in religion_fields:
            return "RELIGION"
        else:
            return "OTHER_PROTECTED"


# Singleton
minor_exclusion_filter = MinorExclusionFilter()
