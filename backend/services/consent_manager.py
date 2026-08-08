"""
Consent Manager Service
Handles consent token lifecycle: creation, expiration, revocation, and audit logging.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from backend.models.consent import ConsentToken, ConsentStatus, AuditLog
from backend.services.finexer_client import finexer_client

logger = logging.getLogger(__name__)

# Default consent validity period
CONSENT_EXPIRY_HOURS = 24 * 90  # 90 days per Open Banking standards


class ConsentManager:
    """
    Manages the full consent token lifecycle.
    Ensures BSA/AML compliance through immutable audit logging.
    """

    async def create_consent(
        self,
        db: AsyncSession,
        applicant_id: uuid.UUID,
        scopes: list[str],
        bank_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentToken:
        """
        Initiate a new consent request.
        Generates authorization URL via Finexer and creates pending consent token.
        """
        # Call Finexer to get authorization URL
        finexer_response = await finexer_client.initiate_consent(
            applicant_id=str(applicant_id),
            scopes=scopes,
            bank_id=bank_id,
        )

        # Create consent token record
        consent_token = ConsentToken(
            applicant_id=applicant_id,
            scopes=scopes,
            status=ConsentStatus.PENDING,
            authorization_url=finexer_response.get("authorization_url"),
            bank_id=bank_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=CONSENT_EXPIRY_HOURS),
        )

        db.add(consent_token)
        await db.flush()

        # Audit log
        await self._audit_log(
            db, consent_token.id, applicant_id, "CONSENT_CREATED",
            {"scopes": scopes, "bank_id": bank_id},
            ip_address, user_agent,
        )

        logger.info(f"Consent token created: {consent_token.id} for applicant {applicant_id}")
        return consent_token

    async def activate_consent(
        self,
        db: AsyncSession,
        consent_token_id: uuid.UUID,
        auth_code: str,
        ip_address: Optional[str] = None,
    ) -> ConsentToken:
        """
        Exchange OAuth code and activate the consent token.
        Called after bank callback with authorization code.
        """
        result = await db.execute(
            select(ConsentToken).where(ConsentToken.id == consent_token_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            raise ValueError(f"Consent token {consent_token_id} not found")

        if consent.status != ConsentStatus.PENDING:
            raise ValueError(f"Consent token is not pending: {consent.status}")

        # Exchange code for tokens
        token_data = await finexer_client.exchange_auth_code(auth_code, str(consent_token_id))

        consent.access_token = token_data.get("access_token")
        consent.refresh_token = token_data.get("refresh_token")
        consent.callback_code = auth_code
        consent.status = ConsentStatus.ACTIVE
        consent.last_accessed_at = datetime.now(timezone.utc)

        await self._audit_log(
            db, consent.id, consent.applicant_id, "CONSENT_ACTIVATED",
            {"token_type": token_data.get("token_type")},
            ip_address,
        )

        logger.info(f"Consent token activated: {consent_token_id}")
        return consent

    async def revoke_consent(
        self,
        db: AsyncSession,
        consent_token_id: uuid.UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ConsentToken:
        """
        Immediately revoke consent: nullify tokens and suspend data access.
        Implements the 'Revocation Logic' from the consent management protocol.
        """
        result = await db.execute(
            select(ConsentToken).where(ConsentToken.id == consent_token_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            raise ValueError(f"Consent token {consent_token_id} not found")

        # Capture previous status before mutation
        previous_status = consent.status.value if hasattr(consent.status, 'value') else str(consent.status)

        # Immediate nullification
        consent.access_token = None
        consent.refresh_token = None
        consent.status = ConsentStatus.REVOKED
        consent.revoked_at = datetime.now(timezone.utc)

        await self._audit_log(
            db, consent.id, consent.applicant_id, "CONSENT_REVOKED",
            {"previous_status": previous_status},
            ip_address, user_agent,
        )

        logger.info(f"Consent token revoked: {consent_token_id}")
        return consent

    async def check_expiration(self, db: AsyncSession, consent_token_id: uuid.UUID) -> bool:
        """
        Check if a consent token has expired.
        Returns True if expired and updates status.
        """
        result = await db.execute(
            select(ConsentToken).where(ConsentToken.id == consent_token_id)
        )
        consent = result.scalar_one_or_none()

        if not consent:
            return True

        if consent.status == ConsentStatus.REVOKED:
            return True

        if consent.expires_at and consent.expires_at < datetime.now(timezone.utc):
            consent.status = ConsentStatus.EXPIRED
            consent.access_token = None
            consent.refresh_token = None

            await self._audit_log(
                db, consent.id, consent.applicant_id, "CONSENT_EXPIRED",
                {"expired_at": consent.expires_at.isoformat()},
            )
            return True

        return False

    async def get_active_consent(
        self, db: AsyncSession, applicant_id: uuid.UUID
    ) -> Optional[ConsentToken]:
        """Get the most recent active consent for an applicant."""
        result = await db.execute(
            select(ConsentToken)
            .where(
                ConsentToken.applicant_id == applicant_id,
                ConsentToken.status == ConsentStatus.ACTIVE,
            )
            .order_by(ConsentToken.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _audit_log(
        self,
        db: AsyncSession,
        consent_token_id: uuid.UUID,
        applicant_id: uuid.UUID,
        action: str,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Write an immutable audit log entry."""
        log = AuditLog(
            consent_token_id=consent_token_id,
            applicant_id=applicant_id,
            action=action,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)


# Singleton
consent_manager = ConsentManager()
