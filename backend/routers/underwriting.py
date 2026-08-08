"""
Multi-Agent Underwriting Router
Module 5: Full underwriting evaluation, decision retrieval, cost reporting, and PDF reports.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.database import get_db
from backend.schemas.underwriting import (
    UnderwritingEvaluateRequest, UnderwritingDecisionResponse,
    AdjustScoreRequest, CostReportResponse, CostReportEntry,
)
from backend.models.underwriting import UnderwritingDecision, AgentOutput, RiskScore
from backend.models.applicant import Applicant
from backend.agents.orchestrator import orchestrator
from backend.services.finexer_client import finexer_client
from backend.services.balance_enrichment import balance_enrichment
from backend.services.correlation_engine import correlation_engine
from backend.services.trajectory_analyzer import trajectory_analyzer
from backend.services.report_generator import generate_report_pdf
from backend.models.biometrics import BiometricSession, TrajectoryPoint
from backend.models.consent import ConsentToken, ConsentStatus
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/underwriting", tags=["Underwriting"])


@router.post("/evaluate")
async def evaluate_applicant(
    req: UnderwritingEvaluateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Full multi-agent underwriting evaluation.
    Triggers all 5 agents and produces a decision with explanations.
    """
    # Verify applicant exists
    app_result = await db.execute(select(Applicant).where(Applicant.id == req.applicant_id))
    applicant = app_result.scalar_one_or_none()
    if not applicant:
        raise HTTPException(404, "Applicant not found")

    # Gather data for each module
    financial_data = None
    osint_data = None
    biometrics_data = None

    # Module 1: Financial data
    if req.include_cashflow:
        consent_result = await db.execute(
            select(ConsentToken)
            .where(
                ConsentToken.applicant_id == req.applicant_id,
                ConsentToken.status == ConsentStatus.ACTIVE,
            )
            .order_by(ConsentToken.created_at.desc())
            .limit(1)
        )
        consent = consent_result.scalar_one_or_none()

        if consent and consent.access_token:
            accounts = await finexer_client.get_accounts(consent.access_token)
            if accounts:
                transactions = await finexer_client.get_transactions(
                    consent.access_token, accounts[0].get("account_id", "")
                )
                balances = await finexer_client.get_balances(
                    consent.access_token, accounts[0].get("account_id", "")
                )
                financial_data = balance_enrichment.analyze_financial_health(transactions)
                financial_data["current_balance"] = balances.get("current_balance", 0)
        else:
            # Use mock data if no consent
            income = applicant.declared_income or 50000.0
            transactions = finexer_client._mock_transactions(income=income)
            balances = finexer_client._mock_balances(income=income)
            financial_data = balance_enrichment.analyze_financial_health(transactions)
            financial_data["current_balance"] = balances.get("current_balance", 0)

    # Module 2: OSINT data
    if req.include_osint:
        osint_data = await correlation_engine.correlate(
            email=applicant.email,
            username=applicant.username,
            pan_number=applicant.pan_number,
            uan_number=applicant.uan_number,
            full_name=applicant.full_name,
        )
        
        # New: Legal Admissibility Certificate
        from backend.services.legal_certification import legal_certification
        digi_payload = osint_data.get("identity_data", {})
        cert_path = legal_certification.generate_65b_certificate(
            applicant_id=str(req.applicant_id),
            osint_payload=osint_data,
            digi_payload=digi_payload,
            device_ip=request.client.host if request.client else "127.0.0.1"
        )
        if cert_path:
            osint_data["legal_certificate_path"] = cert_path

    # Module 3: Biometrics data
    if req.include_biometrics:
        session_result = await db.execute(
            select(BiometricSession)
            .where(BiometricSession.applicant_id == req.applicant_id)
            .order_by(BiometricSession.created_at.desc())
            .limit(1)
        )
        session = session_result.scalar_one_or_none()

        if session and session.analysis_status == "COMPLETED":
            biometrics_data = {
                "bigru_bot_score": session.bigru_bot_score or 0.5,
                "rf_fraud_score": session.rf_fraud_score or 0.5,
                "combined_bot_probability": session.combined_bot_probability or 0.5,
                "mean_velocity": session.mean_velocity,
                "jitter_score": session.jitter_score,
                "path_straightness": session.path_straightness,
                "pause_count": session.pause_count,
                "device_consistent": True,
                "consistency_issues": [],
            }
        else:
            # Default biometrics (neutral)
            biometrics_data = {
                "bigru_bot_score": 0.3,
                "rf_fraud_score": 0.25,
                "combined_bot_probability": 0.28,
                "mean_velocity": 450.0,
                "jitter_score": 35.0,
                "path_straightness": 0.65,
                "pause_count": 5,
                "device_consistent": True,
                "consistency_issues": [],
            }

    # Run the orchestrator
    result = await orchestrator.evaluate(
        applicant_id=str(req.applicant_id),
        financial_data=financial_data,
        osint_data=osint_data,
        biometrics_data=biometrics_data,
        baseline_bureau_score=req.baseline_bureau_score,
        include_cashflow=req.include_cashflow,
        include_osint=req.include_osint,
        include_biometrics=req.include_biometrics,
    )

    # Persist decision
    decision = UnderwritingDecision(
        applicant_id=req.applicant_id,
        decision=result["decision"],
        final_risk_score=result["final_risk_score"],
        adjusted_bureau_score=result.get("adjusted_bureau_score"),
        confidence=result.get("confidence"),
        cashflow_score=result.get("cashflow_score"),
        osint_score=result.get("osint_score"),
        biometric_score=result.get("biometric_score"),
        consumer_explanation=result.get("consumer_explanation"),
        regulator_explanation=result.get("regulator_explanation"),
        contributing_factors=result.get("contributing_factors"),
        total_cost_usd=result.get("total_cost_usd", 0),
        model_tier=result.get("model_tier"),
        total_tokens_used=result.get("total_tokens_used", 0),
        agent_latency_ms=result.get("agent_latency_ms"),
        privacy_budget_spent=result.get("privacy_budget_spent", 0),
        requires_human_review=result.get("requires_human_review", False),
    )
    db.add(decision)
    await db.flush()

    # Store per-agent outputs
    for agent_name, output in result.get("agent_outputs", {}).items():
        agent_out = AgentOutput(
            decision_id=decision.id,
            agent_name=agent_name,
            score=output.get("score"),
            confidence=output.get("confidence"),
            reasoning=output.get("reasoning"),
            raw_output=output,
            contributing_factors=output.get("contributing_factors"),
            tokens_used=output.get("tokens_used", 0),
            cost_usd=0.0,
            model_used=output.get("model_used"),
        )
        db.add(agent_out)

    # Store risk score history
    risk_score = RiskScore(
        applicant_id=req.applicant_id,
        score=result["final_risk_score"],
        score_type="DYNAMIC",
        signal_source="multi_agent_orchestrator",
        adjustment_reason=f"Full evaluation: {result['decision']}",
    )
    db.add(risk_score)

    # Update applicant status
    applicant.application_status = result["decision"]

    result["decision_id"] = str(decision.id)
    return result


@router.get("/decision/{applicant_id}")
async def get_decision(applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get the latest underwriting decision with explanations."""
    result = await db.execute(
        select(UnderwritingDecision)
        .where(UnderwritingDecision.applicant_id == applicant_id)
        .order_by(UnderwritingDecision.created_at.desc())
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(404, "No decision found for this applicant")

    # Load agent outputs
    agents_result = await db.execute(
        select(AgentOutput).where(AgentOutput.decision_id == decision.id)
    )

    return {
        "id": str(decision.id),
        "applicant_id": str(decision.applicant_id),
        "decision": decision.decision,
        "final_risk_score": decision.final_risk_score,
        "adjusted_bureau_score": decision.adjusted_bureau_score,
        "confidence": decision.confidence,
        "cashflow_score": decision.cashflow_score,
        "osint_score": decision.osint_score,
        "biometric_score": decision.biometric_score,
        "consumer_explanation": decision.consumer_explanation,
        "regulator_explanation": decision.regulator_explanation,
        "contributing_factors": decision.contributing_factors,
        "total_cost_usd": decision.total_cost_usd,
        "total_tokens_used": decision.total_tokens_used,
        "agent_latency_ms": decision.agent_latency_ms,
        "requires_human_review": decision.requires_human_review,
        "privacy_budget_spent": decision.privacy_budget_spent,
        "created_at": decision.created_at.isoformat(),
        "agent_outputs": [
            {
                "agent_name": ao.agent_name,
                "score": ao.score,
                "reasoning": ao.reasoning,
                "tokens_used": ao.tokens_used,
                "model_used": ao.model_used,
            }
            for ao in agents_result.scalars()
        ],
    }


@router.get("/cost-report")
async def get_cost_report(db: AsyncSession = Depends(get_db)):
    """Aggregate cost-per-decision analytics."""
    result = await db.execute(
        select(UnderwritingDecision).order_by(UnderwritingDecision.created_at.desc()).limit(100)
    )
    decisions = list(result.scalars())

    if not decisions:
        return {
            "total_decisions": 0,
            "avg_cost_per_decision": 0,
            "total_cost_usd": 0,
            "avg_tokens_per_decision": 0,
            "avg_latency_ms": 0,
            "cost_by_model_tier": {},
            "recent_decisions": [],
        }

    total_cost = sum(d.total_cost_usd or 0 for d in decisions)
    total_tokens = sum(d.total_tokens_used or 0 for d in decisions)
    total_latency = sum(d.agent_latency_ms or 0 for d in decisions)
    n = len(decisions)

    # Group by model tier
    tier_costs = {}
    for d in decisions:
        tier = d.model_tier or "unknown"
        if tier not in tier_costs:
            tier_costs[tier] = {"count": 0, "total_cost": 0}
        tier_costs[tier]["count"] += 1
        tier_costs[tier]["total_cost"] += d.total_cost_usd or 0

    return {
        "total_decisions": n,
        "avg_cost_per_decision": round(total_cost / n, 6),
        "total_cost_usd": round(total_cost, 6),
        "avg_tokens_per_decision": round(total_tokens / n, 0),
        "avg_latency_ms": round(total_latency / n, 0),
        "cost_by_model_tier": tier_costs,
        "recent_decisions": [
            {
                "decision_id": str(d.id),
                "applicant_id": str(d.applicant_id),
                "decision": d.decision,
                "cost_usd": d.total_cost_usd,
                "tokens": d.total_tokens_used,
                "latency_ms": d.agent_latency_ms,
                "created_at": d.created_at.isoformat(),
            }
            for d in decisions[:10]
        ],
    }


@router.get("/download-report/{applicant_id}")
async def download_report(applicant_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Generate and download a professional PDF report for the applicant's
    latest underwriting decision.
    """
    # Fetch latest decision
    result = await db.execute(
        select(UnderwritingDecision)
        .where(UnderwritingDecision.applicant_id == applicant_id)
        .order_by(UnderwritingDecision.created_at.desc())
        .limit(1)
    )
    decision = result.scalar_one_or_none()
    if not decision:
        raise HTTPException(404, "No decision found for this applicant. Run evaluation first.")

    # Load agent outputs
    agents_result = await db.execute(
        select(AgentOutput).where(AgentOutput.decision_id == decision.id)
    )
    agent_outputs = [
        {
            "agent_name": ao.agent_name,
            "score": ao.score,
            "confidence": ao.confidence,
            "reasoning": ao.reasoning,
            "tokens_used": ao.tokens_used,
            "cost_usd": ao.cost_usd,
            "model_used": ao.model_used,
            "contributing_factors": ao.contributing_factors,
        }
        for ao in agents_result.scalars()
    ]

    # Build the same dict shape the frontend already receives
    report_data = {
        "id": str(decision.id),
        "applicant_id": str(decision.applicant_id),
        "decision": decision.decision,
        "final_risk_score": decision.final_risk_score,
        "adjusted_bureau_score": decision.adjusted_bureau_score,
        "confidence": decision.confidence,
        "cashflow_score": decision.cashflow_score,
        "osint_score": decision.osint_score,
        "biometric_score": decision.biometric_score,
        "consumer_explanation": decision.consumer_explanation,
        "regulator_explanation": decision.regulator_explanation,
        "contributing_factors": decision.contributing_factors,
        "total_cost_usd": decision.total_cost_usd,
        "model_tier": decision.model_tier,
        "total_tokens_used": decision.total_tokens_used,
        "agent_latency_ms": decision.agent_latency_ms,
        "requires_human_review": decision.requires_human_review,
        "privacy_budget_spent": decision.privacy_budget_spent,
        "created_at": decision.created_at.isoformat(),
        "agent_outputs": agent_outputs,
    }

    pdf_buffer = generate_report_pdf(report_data)

    filename = f"AIDUS_Report_{applicant_id}_{decision.decision}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
