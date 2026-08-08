"""
PII Redactor
Regex-based PII removal before data enters agentic processing cores.
Supports Indian identity formats (Aadhaar, PAN, phone) and global patterns.
"""

import re
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# PII detection patterns with replacement tokens
PII_PATTERNS: List[Tuple[str, str, str]] = [
    # Indian Aadhaar Number (12 digits, optionally spaced)
    (r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[AADHAAR_REDACTED]", "aadhaar"),
    # Indian PAN Number (ABCDE1234F format)
    (r"\b[A-Z]{5}\d{4}[A-Z]\b", "[PAN_REDACTED]", "pan"),
    # Indian Phone Numbers (+91 or 0 prefix)
    (r"(?:\+91|0)\s?\d{10}\b", "[PHONE_REDACTED]", "phone"),
    # Generic phone (10 digits)
    (r"\b\d{10}\b", "[PHONE_REDACTED]", "phone"),
    # Email addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL_REDACTED]", "email"),
    # Credit card numbers (16 digits, optionally spaced/dashed)
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[CARD_REDACTED]", "credit_card"),
    # Indian bank account numbers (9-18 digits)
    (r"\b\d{9,18}\b", "[ACCOUNT_REDACTED]", "bank_account"),
    # IFSC Code
    (r"\b[A-Z]{4}0[A-Z0-9]{6}\b", "[IFSC_REDACTED]", "ifsc"),
    # UAN (12 digits, matches after other patterns)
    (r"\bUAN\s*:?\s*\d{12}\b", "[UAN_REDACTED]", "uan"),
    # Date of Birth patterns
    (r"\b\d{2}[-/]\d{2}[-/]\d{4}\b", "[DOB_REDACTED]", "dob"),
    # IP Addresses
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP_REDACTED]", "ip_address"),
]


class PIIRedactor:
    """
    Automated PII removal using regex pattern matching.
    Applied as a pre-processing step before data enters agent cores.
    """

    def __init__(self, patterns: List[Tuple[str, str, str]] = None):
        self.patterns = patterns or PII_PATTERNS
        self._compiled = [(re.compile(p), r, t) for p, r, t in self.patterns]

    def redact_text(self, text: str) -> Tuple[str, List[Dict]]:
        """
        Redact all PII from a text string.

        Args:
            text: Input text containing potential PII

        Returns:
            Tuple of (redacted_text, list of redaction events)
        """
        redactions = []
        result = text

        for pattern, replacement, pii_type in self._compiled:
            matches = pattern.findall(result)
            if matches:
                result = pattern.sub(replacement, result)
                for match in matches:
                    redactions.append({
                        "type": pii_type,
                        "replacement": replacement,
                        "original_length": len(match),
                    })

        if redactions:
            logger.info(f"Redacted {len(redactions)} PII instances from text")

        return result, redactions

    def redact_dict(self, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict]]:
        """
        Recursively redact PII from a dictionary's string values.

        Args:
            data: Dictionary potentially containing PII in values

        Returns:
            Tuple of (redacted_dict, list of redaction events)
        """
        all_redactions = []
        result = {}

        for key, value in data.items():
            if isinstance(value, str):
                redacted, redactions = self.redact_text(value)
                result[key] = redacted
                for r in redactions:
                    r["field"] = key
                all_redactions.extend(redactions)
            elif isinstance(value, dict):
                redacted, redactions = self.redact_dict(value)
                result[key] = redacted
                all_redactions.extend(redactions)
            elif isinstance(value, list):
                redacted_list = []
                for item in value:
                    if isinstance(item, str):
                        redacted, redactions = self.redact_text(item)
                        redacted_list.append(redacted)
                        all_redactions.extend(redactions)
                    elif isinstance(item, dict):
                        redacted, redactions = self.redact_dict(item)
                        redacted_list.append(redacted)
                        all_redactions.extend(redactions)
                    else:
                        redacted_list.append(item)
                result[key] = redacted_list
            else:
                result[key] = value

        return result, all_redactions

    def scan_for_pii(self, text: str) -> List[Dict]:
        """Scan text for PII without redacting. Returns list of detected PII types."""
        detected = []
        for pattern, _, pii_type in self._compiled:
            matches = pattern.findall(text)
            if matches:
                detected.append({
                    "type": pii_type,
                    "count": len(matches),
                })
        return detected


# Singleton
pii_redactor = PIIRedactor()
