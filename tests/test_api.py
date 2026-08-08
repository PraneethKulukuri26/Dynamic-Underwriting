"""
Tests for API Endpoints
Covers: Health, Privacy, Biometrics, Consent, OSINT, Underwriting endpoints
"""

import pytest
import uuid
from httpx import AsyncClient


# ============================================================
# HEALTH ENDPOINTS
# ============================================================

class TestHealthEndpoints:
    """Tests for basic health and root endpoints."""

    async def test_health_check(self, client: AsyncClient):
        """Health endpoint should return healthy status."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "AIDUS Backend"

    async def test_root_endpoint(self, client: AsyncClient):
        """Root endpoint should return API overview."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert "docs" in data
        assert data["version"] == "1.0.0"


# ============================================================
# PRIVACY ENDPOINTS
# ============================================================

class TestPrivacyEndpoints:
    """Tests for privacy-related API endpoints."""

    async def test_redact_pii(self, client: AsyncClient):
        """PII redaction endpoint should redact sensitive data."""
        response = await client.post(
            "/api/v1/privacy/redact",
            json={"text": "My email is test@example.com and PAN is ABCDE1234F"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "redacted_text" in data
        assert "test@example.com" not in data["redacted_text"]
        assert "ABCDE1234F" not in data["redacted_text"]

    async def test_add_noise(self, client: AsyncClient):
        """LDP noise endpoint should add calibrated noise."""
        response = await client.post(
            "/api/v1/privacy/noise",
            json={"values": [100.0, 200.0, 300.0], "epsilon": 1.0, "sensitivity": 1.0}
        )
        assert response.status_code == 200
        data = response.json()
        assert "noised_values" in data
        assert len(data["noised_values"]) == 3

    async def test_get_budget(self, client: AsyncClient):
        """Budget endpoint should return budget status."""
        test_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/privacy/budget/{test_id}")
        assert response.status_code == 200
        data = response.json()
        assert "total_spent" in data
        assert "remaining" in data
        assert "max_budget" in data

    async def test_filter_protected(self, client: AsyncClient):
        """Protected characteristics filter should remove sensitive fields."""
        response = await client.post(
            "/api/v1/privacy/filter-protected",
            json={"name": "John", "age": 30, "gender": "male", "income": 50000}
        )
        assert response.status_code == 200
        data = response.json()
        assert "name" in data["filtered_data"]
        assert "income" in data["filtered_data"]
        assert "age" not in data["filtered_data"]
        assert "gender" not in data["filtered_data"]


# ============================================================
# BIOMETRICS ENDPOINTS
# ============================================================

class TestBiometricsEndpoints:
    """Tests for biometrics data ingestion endpoints."""

    async def test_trajectory_batch(self, client: AsyncClient):
        """Trajectory batch endpoint should accept points."""
        response = await client.post(
            "/api/v1/biometrics/trajectory",
            json={
                "session_token": "test_session_123",
                "applicant_id": str(uuid.uuid4()),
                "points": [
                    {"x": 100, "y": 200, "timestamp_ms": 0, "event_type": "move"},
                    {"x": 150, "y": 250, "timestamp_ms": 100, "event_type": "move"},
                ]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "RECEIVED"

    async def test_fingerprint(self, client: AsyncClient):
        """Fingerprint endpoint should process device fingerprint."""
        response = await client.post(
            "/api/v1/biometrics/fingerprint",
            json={
                "session_token": "test_session_123",
                "canvas_hash": "abc123",
                "webgl_hash": "def456",
                "platform": "Win32",
                "screen_resolution": "1920x1080",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_known_device" in data
        assert "consistency_details" in data

    async def test_capi_event(self, client: AsyncClient):
        """CAPI event endpoint should accept deduplication events."""
        response = await client.post(
            "/api/v1/biometrics/event",
            json={
                "event_id": f"evt_{uuid.uuid4().hex[:10]}",
                "event_name": "page_view",
                "session_token": "test_session_123",
                "timestamp": 1700000000,
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "is_duplicate" in data


# ============================================================
# CONSENT ENDPOINTS
# ============================================================

class TestConsentEndpoints:
    """Tests for applicant registration and consent flow."""

    async def test_create_applicant(self, client: AsyncClient):
        """Applicant creation should return applicant data."""
        response = await client.post(
            "/api/v1/applicants",
            json={
                "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
                "phone": "+91 9876543210",
                "full_name": "Test User",
                "username": f"testuser_{uuid.uuid4().hex[:8]}",
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["email"].endswith("@example.com")

    async def test_create_applicant_duplicate_email(self, client: AsyncClient):
        """Duplicate email should return existing applicant."""
        email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        # Create first
        await client.post("/api/v1/applicants", json={"email": email})
        # Create again with same email
        response = await client.post("/api/v1/applicants", json={"email": email})
        assert response.status_code == 200

    async def test_consent_status_nonexistent(self, client: AsyncClient):
        """Non-existent consent token should return 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/consent/status/{fake_id}")
        assert response.status_code == 404

    async def test_consent_revoke_nonexistent(self, client: AsyncClient):
        """Revoking non-existent consent should return 404."""
        fake_id = str(uuid.uuid4())
        response = await client.post(f"/api/v1/consent/revoke/{fake_id}")
        assert response.status_code == 404


# ============================================================
# OSINT ENDPOINTS
# ============================================================

class TestOSINTEndpoints:
    """Tests for OSINT pipeline endpoints."""

    async def test_username_search(self, client: AsyncClient):
        """Username search should return platform matches."""
        response = await client.post(
            "/api/v1/osint/username-search",
            json={"username": "testuser123"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "platforms" in data
        assert "total_found" in data

    async def test_breach_check(self, client: AsyncClient):
        """Breach check should return breach records."""
        response = await client.post(
            "/api/v1/osint/breach-check",
            json={"email": "test@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "breaches" in data
        assert "total_breaches" in data

    async def test_verify_identity(self, client: AsyncClient):
        """Identity verification should return verification results."""
        response = await client.post(
            "/api/v1/osint/verify-identity",
            json={"pan_number": "ABCDE1234F"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "verification_details" in data


# ============================================================
# UNDERWRITING ENDPOINTS
# ============================================================

class TestUnderwritingEndpoints:
    """Tests for underwriting evaluation endpoints."""

    async def test_cost_report_empty(self, client: AsyncClient):
        """Cost report with no decisions should return zeros."""
        response = await client.get("/api/v1/underwriting/cost-report")
        assert response.status_code == 200
        data = response.json()
        assert data["total_decisions"] == 0
        assert data["avg_cost_per_decision"] == 0

    async def test_decision_nonexistent(self, client: AsyncClient):
        """Non-existent decision should return 404."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/underwriting/decision/{fake_id}")
        assert response.status_code == 404
