"""
AIDUS Underwriting Report Generator
Generates publication-quality PDF reports from underwriting decision JSON.
Follows the standardized AIDUS schema with six technical layers.
"""

import io
import logging
import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)

# ── Color Palette ──────────────────────────────────────────
C_PRIMARY   = HexColor("#1a237e")
C_APPROVED  = HexColor("#1b5e20")
C_DENIED    = HexColor("#b71c1c")
C_REVIEW    = HexColor("#e65100")
C_POSITIVE  = HexColor("#2e7d32")
C_NEGATIVE  = HexColor("#c62828")
C_NEUTRAL   = HexColor("#757575")
C_LIGHT_BG  = HexColor("#f5f5f5")
C_ALT_BG    = HexColor("#e8eaf6")
C_BORDER    = HexColor("#bdbdbd")
C_TEXT      = HexColor("#212121")
C_MUTED     = HexColor("#616161")
C_WHITE     = HexColor("#ffffff")
C_DARK_BG   = HexColor("#263238")

DECISION_COLORS = {
    "APPROVED": C_APPROVED,
    "DENIED": C_DENIED,
    "REJECTED": C_DENIED,
    "REVIEW_REQUIRED": C_REVIEW,
}


def _ascii_bar(score: Optional[float], width: int = 20) -> str:
    """Render an ASCII progress bar: ■■■■■■□□□□ (60%)"""
    if score is None:
        return "N/A"
    clamped = max(0.0, min(1.0, score))
    filled = round(clamped * width)
    empty = width - filled
    pct = int(clamped * 100)
    return f"{'■' * filled}{'□' * empty}  ({pct}%)"


def _impact_color(impact: str) -> HexColor:
    if impact == "POSITIVE":
        return C_POSITIVE
    elif impact == "NEGATIVE":
        return C_NEGATIVE
    return C_NEUTRAL


def _fmt_timestamp(raw: str) -> str:
    """Parse ISO timestamp to human-readable UTC."""
    if not raw:
        return "N/A"
    try:
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        return raw
    except Exception:
        return raw


def _build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="RTitle",
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=C_PRIMARY,
        spaceAfter=4,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="RSubTitle",
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=C_MUTED,
        spaceAfter=14,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="DecBanner",
        fontName="Helvetica-Bold",
        fontSize=16,
        spaceAfter=4,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="ScoreLine",
        fontName="Helvetica",
        fontSize=10,
        textColor=C_TEXT,
        spaceAfter=12,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="SectionH",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=C_PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        name="SubSectionH",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=C_PRIMARY,
        spaceBefore=8,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Body",
        fontName="Helvetica",
        fontSize=9,
        textColor=C_TEXT,
        leading=13,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall",
        fontName="Helvetica",
        fontSize=8,
        textColor=C_TEXT,
        leading=11,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        name="Mono",
        fontName="Courier",
        fontSize=8,
        textColor=C_TEXT,
        leading=10,
        spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="Quote",
        fontName="Helvetica",
        fontSize=9,
        textColor=C_TEXT,
        leading=13,
        leftIndent=16,
        rightIndent=8,
        spaceAfter=6,
        borderPadding=6,
    ))
    styles.add(ParagraphStyle(
        name="Footer",
        fontName="Helvetica",
        fontSize=7,
        textColor=C_MUTED,
        alignment=TA_CENTER,
        spaceBefore=16,
    ))
    return styles


def _make_table(data: list, col_widths: Optional[list] = None, header_bg=C_PRIMARY) -> Table:
    """Create a styled table with alternating row backgrounds."""
    table = Table(data, colWidths=col_widths, hAlign="LEFT")
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("BACKGROUND", (0, 1), (-1, -1), C_WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT_BG]),
        ("TEXTCOLOR", (0, 1), (-1, -1), C_TEXT),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, C_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    table.setStyle(TableStyle(style_cmds))
    return table


def generate_report_pdf(data: Dict[str, Any]) -> io.BytesIO:
    """
    Generate a publication-quality AIDUS Underwriting Report PDF.

    Follows the six-layer schema:
      A. Strategic Metadata Header
      B. Visual Agent Score Breakdown (ASCII bar charts)
      C. Contributing Factors Matrix
      D. Dual-Explanation Block
      E. Sub-Agent Diagnostic Outputs
      F. Compliance Footer
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    styles = _build_styles()
    elements: list = []

    # ── Extract fields ──────────────────────────────────────
    decision       = data.get("decision", "UNKNOWN")
    risk_score     = data.get("final_risk_score", 0.0)
    confidence     = data.get("confidence", 0.0)
    applicant_id   = data.get("applicant_id", "N/A")
    adj_bureau     = data.get("adjusted_bureau_score")
    model_tier     = data.get("model_tier", "N/A")
    cost_usd       = data.get("total_cost_usd", 0.0)
    tokens         = data.get("total_tokens_used", 0)
    latency_ms     = data.get("agent_latency_ms", 0)
    privacy_eps    = data.get("privacy_budget_spent", 0.0)
    human_review   = data.get("requires_human_review", False)
    created_at     = _fmt_timestamp(data.get("created_at", ""))
    cf_score       = data.get("cashflow_score")
    osint_score    = data.get("osint_score")
    bio_score      = data.get("biometric_score")
    consumer_exp   = data.get("consumer_explanation", "")
    regulator_exp  = data.get("regulator_explanation", "")
    factors        = data.get("contributing_factors", [])
    agent_outputs  = data.get("agent_outputs", [])

    dec_color = DECISION_COLORS.get(decision, C_NEUTRAL)

    # ══════════════════════════════════════════════════════════
    # LAYER A — Strategic Metadata Header
    # ══════════════════════════════════════════════════════════
    elements.append(Paragraph("AIDUS Underwriting Report", styles["RTitle"]))
    elements.append(Paragraph(
        "AI-Driven Dynamic Underwriting System  |  Confidential",
        styles["RSubTitle"],
    ))
    elements.append(HRFlowable(width="100%", thickness=2, color=C_PRIMARY))
    elements.append(Spacer(1, 8))

    # Decision banner
    dec_style = ParagraphStyle("DecColor", parent=styles["DecBanner"], textColor=dec_color)
    elements.append(Paragraph(f"Decision: {decision}", dec_style))

    # Score + confidence line
    conf_pct = f"{confidence:.2%}" if isinstance(confidence, (int, float)) else "N/A"
    elements.append(Paragraph(
        f"Risk Score: {risk_score:.4f}  |  Confidence: {conf_pct}",
        styles["ScoreLine"],
    ))
    elements.append(Spacer(1, 4))

    # Table 1 — Application & Telemetry Summary
    elements.append(Paragraph("I. Application &amp; Telemetry Summary", styles["SectionH"]))

    summary_rows = [
        ["Metric Parameter", "Ingested System Value"],
        ["Applicant ID", str(applicant_id)],
        ["Decision Outcome", decision],
        ["Final Synthesized Risk Score", f"{risk_score:.4f}"],
        ["Adjusted Bureau Score", str(adj_bureau) if adj_bureau is not None else "N/A"],
        ["System Classification Confidence", conf_pct],
        ["Model Tier Utilized", str(model_tier)],
        ["Total Incurred Cost (USD)", f"${cost_usd:.6f}"],
        ["Cumulative Tokens Consumed", str(tokens)],
        ["Core Agent Latency (ms)", str(latency_ms)],
        ["Session Privacy Budget Spent", f"{privacy_eps:.4f}"],
        ["Requires Human Intervention", "Yes" if human_review else "No"],
        ["Timestamp (UTC)", created_at],
    ]
    elements.append(_make_table(summary_rows, col_widths=[2.8 * inch, 4.2 * inch]))
    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════
    # LAYER B — Visual Agent Score Breakdown (ASCII Bar Charts)
    # ══════════════════════════════════════════════════════════
    elements.append(Paragraph("II. Microservice Risk Breakdown", styles["SectionH"]))

    # Weights from orchestrator
    weights = {"cashflow": 0.35, "osint": 0.25, "biometrics": 0.25, "selfcheck": 0.15}

    agents_visual = [
        ("Cashflow Agent Risk",   cf_score,    weights["cashflow"]),
        ("OSINT Agent Risk",      osint_score, weights["osint"]),
        ("Biometrics Agent Risk", bio_score,   weights["biometrics"]),
    ]

    for label, score, weight in agents_visual:
        bar = _ascii_bar(score)
        score_str = f"{score:.4f}" if score is not None else "N/A"
        weight_pct = f"{int(weight * 100)}%"
        elements.append(Paragraph(
            f"<b>{label}:</b>  {score_str}  |  <font face='Courier'>{bar}</font>  ({weight_pct})",
            styles["Body"],
        ))
    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════
    # LAYER C — Contributing Factors Matrix
    # ══════════════════════════════════════════════════════════
    elements.append(Paragraph("III. Contributing Underwriting Factors", styles["SectionH"]))

    if factors:
        factor_rows = [["Risk Factor", "Weight", "Provenance Source", "Model Impact", "Telemetry Details &amp; Heuristics"]]
        for f in factors:
            factor_rows.append([
                f.get("factor", "N/A"),
                f"{f.get('weight', 0):.2f}",
                f.get("source", "N/A"),
                f.get("impact", "N/A"),
                (f.get("details", "") or "")[:100],
            ])
        elements.append(_make_table(factor_rows, col_widths=[1.1*inch, 0.6*inch, 0.9*inch, 0.9*inch, 3.5*inch]))
    else:
        elements.append(Paragraph("<i>No contributing factors recorded.</i>", styles["BodySmall"]))
    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════
    # LAYER D — Dual-Explanation Block
    # ══════════════════════════════════════════════════════════
    elements.append(Paragraph("IV. Compliance &amp; Decision Explanations", styles["SectionH"]))

    # Consumer
    elements.append(Paragraph("Consumer-Facing Explanation", styles["SubSectionH"]))
    if consumer_exp:
        elements.append(Paragraph(consumer_exp, styles["Quote"]))
    else:
        elements.append(Paragraph("<i>No consumer explanation available.</i>", styles["BodySmall"]))

    elements.append(Spacer(1, 6))

    # Regulator
    elements.append(Paragraph("Regulatory Audit Disclosure (Regulator-Facing)", styles["SubSectionH"]))
    if regulator_exp:
        # Build the regulator block with structured sub-elements
        reg_lines = regulator_exp.split(". ")
        for line in reg_lines:
            line = line.strip()
            if line:
                elements.append(Paragraph(line + ".", styles["BodySmall"]))
    else:
        elements.append(Paragraph("<i>No regulator explanation available.</i>", styles["BodySmall"]))

    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════
    # LAYER E — Sub-Agent Diagnostic Outputs
    # ══════════════════════════════════════════════════════════
    elements.append(Paragraph("V. Sub-Agent Diagnostic Outputs", styles["SectionH"]))

    if agent_outputs:
        for agent in agent_outputs:
            name      = agent.get("agent_name", "unknown").upper()
            a_score   = agent.get("score")
            a_model   = agent.get("model_used", "N/A")
            a_tokens  = agent.get("tokens_used", 0)
            reasoning = agent.get("reasoning", "")

            score_str = f"{a_score:.4f}" if a_score is not None else "N/A"

            # Agent header line
            elements.append(Paragraph(
                f"<b>{name}</b>  |  Risk Score: {score_str}  |  Model: {a_model}",
                styles["Body"],
            ))
            # Reasoning block as diagnostic log
            if reasoning:
                elements.append(Paragraph(
                    f"[Diagnostic Log: {reasoning[:400]}]",
                    styles["Mono"],
                ))
            elements.append(Spacer(1, 6))
    else:
        elements.append(Paragraph("<i>No sub-agent outputs recorded.</i>", styles["BodySmall"]))

    # ══════════════════════════════════════════════════════════
    # LAYER F — Compliance Footer
    # ══════════════════════════════════════════════════════════
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=1, color=C_BORDER))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "Report automatically compiled by AIDUS Dynamic Underwriting Platform v1.0.0. "
        "All transactions sanitized in local runtime memory. Apache 2.0 Licensing applied.",
        styles["Footer"],
    ))
    elements.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  "
        f"Applicant: {applicant_id}",
        styles["Footer"],
    ))

    # Build PDF
    doc.build(elements)
    buf.seek(0)
    return buf
