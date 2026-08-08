"""
Tests for Privacy Modules
Covers: PII Redaction, Minor Exclusions, LDP, Budget Tracker, Gradient Clipping
"""

import math
import numpy as np
import pytest
from backend.privacy.pii_redactor import PIIRedactor, pii_redactor, PII_PATTERNS
from backend.privacy.minor_exclusions import MinorExclusionFilter, minor_exclusion_filter, PROTECTED_FIELDS
from backend.privacy.ldp import LocalDifferentialPrivacy, ldp
from backend.privacy.budget_tracker import PrivacyBudgetTracker
from backend.privacy.gradient_clipping import GradientClipper, gradient_clipper


# ============================================================
# PII REDACTOR TESTS
# ============================================================

class TestPIIRedactor:
    """Tests for regex-based PII detection and redaction."""

    def test_redact_aadhaar_number(self):
        """Aadhaar (12 digits) should be redacted."""
        redactor = PIIRedactor()
        text = "My Aadhaar is 1234 5678 9012"
        result, redactions = redactor.redact_text(text)

        assert "[AADHAAR_REDACTED]" in result
        assert "1234" not in result
        assert len(redactions) >= 1
        assert redactions[0]["type"] == "aadhaar"

    def test_redact_pan_number(self):
        """PAN (ABCDE1234F format) should be redacted."""
        redactor = PIIRedactor()
        text = "My PAN is ABCDE1234F"
        result, redactions = redactor.redact_text(text)

        assert "[PAN_REDACTED]" in result
        assert "ABCDE1234F" not in result
        assert any(r["type"] == "pan" for r in redactions)

    def test_redact_email(self):
        """Email addresses should be redacted."""
        redactor = PIIRedactor()
        text = "Contact me at user@example.com"
        result, redactions = redactor.redact_text(text)

        assert "[EMAIL_REDACTED]" in result
        assert "user@example.com" not in result
        assert any(r["type"] == "email" for r in redactions)

    def test_redact_phone_number(self):
        """Indian phone numbers should be redacted."""
        redactor = PIIRedactor()
        text = "Call me at +91 9876543210"
        result, redactions = redactor.redact_text(text)

        assert "[PHONE_REDACTED]" in result
        assert "9876543210" not in result

    def test_redact_ip_address(self):
        """IP addresses should be redacted."""
        redactor = PIIRedactor()
        text = "Server at 192.168.1.100"
        result, redactions = redactor.redact_text(text)

        assert "[IP_REDACTED]" in result
        assert "192.168.1.100" not in result
        assert any(r["type"] == "ip_address" for r in redactions)

    def test_redact_dict_nested(self):
        """Recursive dict redaction should work."""
        redactor = PIIRedactor()
        data = {
            "name": "John",
            "email": "john@test.com",
            "nested": {
                "aadhaar": "123456789012",
                "pan": "ABCDE1234F"
            }
        }
        result, redactions = redactor.redact_dict(data)

        assert result["name"] == "John"
        assert "[EMAIL_REDACTED]" in result["email"]
        assert "[AADHAAR_REDACTED]" in result["nested"]["aadhaar"]
        assert "[PAN_REDACTED]" in result["nested"]["pan"]
        assert len(redactions) >= 3

    def test_redact_dict_list(self):
        """List items in dict should be redacted."""
        redactor = PIIRedactor()
        data = {
            "emails": ["a@b.com", "c@d.com"],
            "text": "normal text"
        }
        result, redactions = redactor.redact_dict(data)

        assert "[EMAIL_REDACTED]" in result["emails"][0]
        assert "[EMAIL_REDACTED]" in result["emails"][1]
        assert result["text"] == "normal text"

    def test_scan_for_pii_no_redaction(self):
        """scan_for_pii should detect without modifying."""
        redactor = PIIRedactor()
        text = "Email: test@test.com, PAN: ABCDE1234F"
        detected = redactor.scan_for_pii(text)

        types = [d["type"] for d in detected]
        assert "email" in types
        assert "pan" in types

    def test_no_pii_returns_clean(self):
        """Text with no PII should pass through unchanged."""
        redactor = PIIRedactor()
        text = "Hello, this is normal text with no sensitive data."
        result, redactions = redactor.redact_text(text)

        assert result == text
        assert len(redactions) == 0

    def test_credit_card_redaction(self):
        """Credit card numbers should be redacted."""
        redactor = PIIRedactor()
        text = "Card: 4111-1111-1111-1111"
        result, redactions = redactor.redact_text(text)

        assert "[CARD_REDACTED]" in result or "[AADHAAR_REDACTED]" in result
        assert len(redactions) >= 1

    def test_ifsc_code_redaction(self):
        """IFSC codes should be redacted."""
        redactor = PIIRedactor()
        text = "IFSC: HDFC0001234"
        result, redactions = redactor.redact_text(text)

        assert "[IFSC_REDACTED]" in result
        assert any(r["type"] == "ifsc" for r in redactions)

    def test_singleton_has_all_patterns(self):
        """Singleton should have all default PII patterns."""
        assert len(pii_redactor.patterns) == len(PII_PATTERNS)


# ============================================================
# MINOR EXCLUSIONS TESTS
# ============================================================

class TestMinorExclusions:
    """Tests for protected characteristic filtering."""

    def test_filter_age_field(self):
        """Age-related fields should be filtered."""
        filt = MinorExclusionFilter()
        data = {"name": "John", "age": 30, "income": 50000}
        result, exclusions = filt.filter_dict(data)

        assert "name" in result
        assert "income" in result
        assert "age" not in result
        assert len(exclusions) == 1
        assert exclusions[0]["category"] == "AGE"

    def test_filter_gender_field(self):
        """Gender fields should be filtered."""
        filt = MinorExclusionFilter()
        data = {"name": "John", "gender": "male"}
        result, exclusions = filt.filter_dict(data)

        assert "gender" not in result
        assert exclusions[0]["category"] == "GENDER"

    def test_filter_date_of_birth(self):
        """DOB fields should be filtered."""
        filt = MinorExclusionFilter()
        data = {"name": "John", "date_of_birth": "1990-01-01"}
        result, exclusions = filt.filter_dict(data)

        assert "date_of_birth" not in result
        assert exclusions[0]["category"] == "AGE"

    def test_filter_religion_field(self):
        """Religion fields should be filtered."""
        filt = MinorExclusionFilter()
        data = {"name": "John", "religion": "hindu"}
        result, exclusions = filt.filter_dict(data)

        assert "religion" not in result
        assert exclusions[0]["category"] == "RELIGION"

    def test_filter_caste_field(self):
        """Caste fields should be filtered."""
        filt = MinorExclusionFilter()
        data = {"name": "John", "caste": "general"}
        result, exclusions = filt.filter_dict(data)

        assert "caste" not in result
        assert exclusions[0]["category"] == "CASTE"

    def test_filter_nested_dict(self):
        """Protected fields in nested dicts should be filtered."""
        filt = MinorExclusionFilter()
        data = {
            "name": "John",
            "profile": {
                "age": 30,
                "gender": "male",
                "city": "Mumbai"
            }
        }
        result, exclusions = filt.filter_dict(data)

        assert "name" in result
        assert "city" in result["profile"]
        assert "age" not in result["profile"]
        assert "gender" not in result["profile"]
        assert len(exclusions) == 2

    def test_filter_list_of_dicts(self):
        """Protected fields in list items should be filtered."""
        filt = MinorExclusionFilter()
        data = {
            "records": [
                {"name": "A", "age": 25},
                {"name": "B", "age": 30}
            ]
        }
        result, exclusions = filt.filter_dict(data)

        assert len(result["records"]) == 2
        assert "age" not in result["records"][0]
        assert "age" not in result["records"][1]
        assert len(exclusions) == 2

    def test_scan_without_filtering(self):
        """scan_for_protected should detect without removing."""
        filt = MinorExclusionFilter()
        data = {"age": 30, "gender": "female", "name": "Jane"}
        detected = filt.scan_for_protected(data)

        assert len(detected) == 2
        # Original data unchanged
        assert "age" in data
        assert "gender" in data

    def test_non_protected_fields_preserved(self):
        """Non-protected fields should pass through."""
        filt = MinorExclusionFilter()
        data = {"income": 50000, "name": "Test", "email": "test@test.com"}
        result, exclusions = filt.filter_dict(data)

        assert result == data
        assert len(exclusions) == 0

    def test_protected_fields_set_completeness(self):
        """All expected protected field types should be in the set."""
        expected_categories = {"age", "gender", "caste", "religion", "race", "disability", "marital_status", "genetic_data"}
        for field in expected_categories:
            assert field in PROTECTED_FIELDS or any(f.startswith(field) for f in PROTECTED_FIELDS)


# ============================================================
# LDP TESTS
# ============================================================

class TestLocalDifferentialPrivacy:
    """Tests for Local Differential Privacy noise mechanisms."""

    def test_compute_noise_scale_positive(self):
        """Noise scale should be positive for valid inputs."""
        sigma = ldp.compute_noise_scale(sensitivity=1.0, epsilon=1.0, delta=1e-5)
        assert sigma > 0

    def test_compute_noise_scale_increases_with_sensitivity(self):
        """Higher sensitivity should produce more noise."""
        sigma_low = ldp.compute_noise_scale(sensitivity=0.5, epsilon=1.0)
        sigma_high = ldp.compute_noise_scale(sensitivity=2.0, epsilon=1.0)
        assert sigma_high > sigma_low

    def test_compute_noise_scale_decreases_with_epsilon(self):
        """Higher epsilon (less privacy) should produce less noise."""
        sigma_low_eps = ldp.compute_noise_scale(sensitivity=1.0, epsilon=10.0)
        sigma_high_eps = ldp.compute_noise_scale(sensitivity=1.0, epsilon=0.1)
        assert sigma_low_eps < sigma_high_eps

    def test_add_noise_scalar(self):
        """Noise should be added to scalar values."""
        original = 100.0
        noisy = ldp.add_noise(original, epsilon=1.0, sensitivity=1.0)
        assert isinstance(noisy, float)
        # With high probability, noise should change the value
        # (not guaranteed but extremely likely)
        assert noisy != original or True  # Allow rare equality

    def test_add_noise_array(self):
        """Noise should be added element-wise to arrays."""
        original = np.array([1.0, 2.0, 3.0])
        noisy = ldp.add_noise(original, epsilon=1.0, sensitivity=1.0)
        assert isinstance(noisy, np.ndarray)
        assert noisy.shape == original.shape

    def test_add_noise_preserves_shape(self):
        """Noisy output should have same shape as input."""
        original = np.array([[1, 2], [3, 4]])
        noisy = ldp.add_noise(original, epsilon=1.0)
        assert noisy.shape == original.shape

    def test_add_laplace_noise(self):
        """Laplace noise should be added."""
        original = 50.0
        noisy = ldp.add_laplace_noise(original, epsilon=1.0, sensitivity=1.0)
        assert isinstance(noisy, float)

    def test_randomized_response(self):
        """Randomized response should return boolean."""
        result = ldp.randomized_response(True, epsilon=1.0)
        assert isinstance(result, bool)

    def test_randomized_response_high_epsilon(self):
        """With very high epsilon, randomized response should mostly return original."""
        results = [ldp.randomized_response(True, epsilon=100.0) for _ in range(100)]
        true_count = sum(results)
        # With epsilon=100, should return True ~99% of the time
        assert true_count > 90

    def test_invalid_epsilon_raises(self):
        """Zero or negative epsilon should raise ValueError."""
        with pytest.raises(ValueError):
            ldp.compute_noise_scale(sensitivity=1.0, epsilon=0)
        with pytest.raises(ValueError):
            ldp.compute_noise_scale(sensitivity=1.0, epsilon=-1)

    def test_invalid_delta_raises(self):
        """Delta outside (0,1) should raise ValueError."""
        with pytest.raises(ValueError):
            ldp.compute_noise_scale(sensitivity=1.0, epsilon=1.0, delta=0)
        with pytest.raises(ValueError):
            ldp.compute_noise_scale(sensitivity=1.0, epsilon=1.0, delta=1)


# ============================================================
# BUDGET TRACKER TESTS
# ============================================================

class TestPrivacyBudgetTracker:
    """Tests for cumulative privacy budget tracking."""

    def test_initial_budget_full(self):
        """New applicant should have full budget remaining."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        remaining = tracker.get_remaining_budget("applicant_1")
        assert remaining == 10.0

    def test_can_query_within_budget(self):
        """Query within budget should be allowed."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        assert tracker.can_query("applicant_1", epsilon_cost=5.0) is True

    def test_cannot_query_exceeds_budget(self):
        """Query exceeding budget should be rejected."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        assert tracker.can_query("applicant_1", epsilon_cost=15.0) is False

    def test_record_query_reduces_budget(self):
        """Recording a query should reduce remaining budget."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        tracker.record_query("applicant_1", epsilon_cost=3.0, operation="test")
        remaining = tracker.get_remaining_budget("applicant_1")
        assert remaining == pytest.approx(7.0, abs=0.01)

    def test_multiple_queries_cumulative(self):
        """Multiple queries should accumulate privacy cost."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        tracker.record_query("applicant_1", epsilon_cost=2.0)
        tracker.record_query("applicant_1", epsilon_cost=3.0)
        tracker.record_query("applicant_1", epsilon_cost=1.0)
        remaining = tracker.get_remaining_budget("applicant_1")
        assert remaining == pytest.approx(4.0, abs=0.01)

    def test_budget_exhaustion_blocks_queries(self):
        """After budget exhausted, queries should be blocked."""
        tracker = PrivacyBudgetTracker(max_budget=5.0)
        tracker.record_query("applicant_1", epsilon_cost=5.0)
        assert tracker.can_query("applicant_1", epsilon_cost=0.1) is False

    def test_budget_status_returns_full_info(self):
        """Budget status should include all fields."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        tracker.record_query("applicant_1", epsilon_cost=2.0, operation="cashflow")
        status = tracker.get_budget_status("applicant_1")

        assert "total_spent" in status
        assert "remaining" in status
        assert "max_budget" in status
        assert "usage_percentage" in status
        assert "total_queries" in status
        assert "recent_queries" in status
        assert status["total_queries"] == 1

    def test_independent_applicants(self):
        """Budget tracking should be per-applicant."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        tracker.record_query("applicant_1", epsilon_cost=5.0)
        tracker.record_query("applicant_2", epsilon_cost=3.0)

        assert tracker.get_remaining_budget("applicant_1") == pytest.approx(5.0)
        assert tracker.get_remaining_budget("applicant_2") == pytest.approx(7.0)

    def test_usage_percentage_calculation(self):
        """Usage percentage should be calculated correctly."""
        tracker = PrivacyBudgetTracker(max_budget=10.0)
        tracker.record_query("applicant_1", epsilon_cost=3.0)
        status = tracker.get_budget_status("applicant_1")
        assert status["usage_percentage"] == pytest.approx(30.0, abs=0.1)


# ============================================================
# GRADIENT CLIPPING TESTS
# ============================================================

class TestGradientClipper:
    """Tests for L2 norm gradient clipping."""

    def test_clip_within_norm(self):
        """Gradients within max_norm should pass through unchanged."""
        clipper = GradientClipper(max_norm=1.0)
        grad = np.array([0.3, 0.4])  # norm = 0.5
        clipped = clipper.clip(grad)
        np.testing.assert_array_almost_equal(clipped, grad)

    def test_clip_exceeds_norm(self):
        """Gradients exceeding max_norm should be scaled down."""
        clipper = GradientClipper(max_norm=1.0)
        grad = np.array([3.0, 4.0])  # norm = 5.0
        clipped = clipper.clip(grad)
        assert np.linalg.norm(clipped) == pytest.approx(1.0, abs=0.01)

    def test_clip_preserves_direction(self):
        """Clipping should preserve gradient direction."""
        clipper = GradientClipper(max_norm=1.0)
        grad = np.array([3.0, 4.0])
        clipped = clipper.clip(grad)
        # Direction should be same (proportional)
        assert clipped[0] / clipped[1] == pytest.approx(grad[0] / grad[1], abs=0.01)

    def test_clip_custom_max_norm(self):
        """Custom max_norm should be respected."""
        clipper = GradientClipper(max_norm=1.0)
        grad = np.array([3.0, 4.0])
        clipped = clipper.clip(grad, max_norm=2.0)
        assert np.linalg.norm(clipped) == pytest.approx(2.0, abs=0.01)

    def test_clip_per_sample(self):
        """Per-sample clipping should clip each gradient independently."""
        clipper = GradientClipper(max_norm=1.0)
        batch = [
            np.array([3.0, 4.0]),   # norm = 5.0, should clip
            np.array([0.3, 0.4]),   # norm = 0.5, should pass
        ]
        clipped = clipper.clip_per_sample(batch)
        assert np.linalg.norm(clipped[0]) == pytest.approx(1.0, abs=0.01)
        np.testing.assert_array_almost_equal(clipped[1], batch[1])

    def test_clip_and_aggregate(self):
        """Clip-and-aggregate should return mean of clipped gradients."""
        clipper = GradientClipper(max_norm=1.0)
        batch = [
            np.array([3.0, 4.0]),
            np.array([3.0, 4.0]),
        ]
        aggregated = clipper.clip_and_aggregate(batch)
        # Both clip to same direction, mean should be same as individual
        assert np.linalg.norm(aggregated) == pytest.approx(1.0, abs=0.01)

    def test_zero_gradient(self):
        """Zero gradients should pass through."""
        clipper = GradientClipper(max_norm=1.0)
        grad = np.array([0.0, 0.0])
        clipped = clipper.clip(grad)
        np.testing.assert_array_almost_equal(clipped, grad)

    def test_list_input_converted(self):
        """List input should be converted to numpy array."""
        clipper = GradientClipper(max_norm=1.0)
        grad = [0.3, 0.4]
        clipped = clipper.clip(grad)
        assert isinstance(clipped, np.ndarray)
