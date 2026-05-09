from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm


def render_brsr_pdf(context: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Demo watermark
    if context.get("is_seed_data"):
        story.append(Paragraph(
            "⚠ DEMO DATA — NOT FOR SUBMISSION",
            ParagraphStyle('warn', parent=styles['Heading1'],
                           textColor=colors.red, fontSize=14)
        ))
        story.append(Spacer(1, 0.5*cm))

    # Header
    story.append(Paragraph(
        f"BRSR Section C — Principle 9",
        styles['Heading1']
    ))
    story.append(Paragraph(
        f"{context.get('organisation_name', '')} | {context.get('facility_name', '')} | {context.get('fy_label', '')}",
        styles['Normal']
    ))
    story.append(Paragraph(
        f"Generated: {context.get('reporting_date', '')}",
        styles['Normal']
    ))
    story.append(Spacer(1, 1*cm))

    # KPI 1 — GHG
    story.append(Paragraph("KPI 1: GHG Footprint (tCO₂e)", styles['Heading2']))
    kpi1 = context.get("kpi1", {})
    kpi1_data = [
        ["Scope", "Value (tCO₂e)"],
        ["Scope 1 — Process", str(round(float(kpi1.get("scope1_process_tco2e") or 0), 2))],
        ["Scope 1 — Combustion", str(round(float(kpi1.get("scope1_combustion_tco2e") or 0), 2))],
        ["Scope 2 — Grid Electricity", str(round(float(kpi1.get("scope2_tco2e") or 0), 2))],
        ["TOTAL", str(round(float(kpi1.get("total_tco2e") or 0), 2))],
    ]
    t1 = Table(kpi1_data, colWidths=[10*cm, 6*cm])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f5e9')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(t1)
    story.append(Spacer(1, 1*cm))

    # KPI 3 — Energy
    story.append(Paragraph("KPI 3: Energy Footprint", styles['Heading2']))
    kpi3 = context.get("kpi3", {})
    kpi3_data = [
        ["Metric", "Value"],
        ["Total Energy (GJ)", str(round(float(kpi3.get("total_energy_GJ") or 0), 2))],
        ["Energy Intensity (GJ/tonne)", str(round(float(kpi3.get("energy_intensity_GJ_per_tonne") or 0), 4))],
    ]
    if context.get("has_unsupported_fuel"):
        kpi3_data.append(["⚠ Note", "Energy total incomplete — non-diesel fuel excluded"])

    t3 = Table(kpi3_data, colWidths=[10*cm, 6*cm])
    t3.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    story.append(t3)
    story.append(Spacer(1, 1*cm))

    # Methodology footnote
    story.append(Paragraph("Methodology", styles['Heading3']))
    story.append(Paragraph(
        context.get("calculation_methodology", ""),
        styles['Normal']
    ))
    story.append(Paragraph(
        "Emission factors: IPCC 2006 Vol 2 & 3, CEA FY2023-24. "
        "Grid factor: 0.716 tCO₂/MWh (CEA). "
        "Diesel: 2.651 kgCO₂/L (IPCC 2006).",
        styles['Normal']
    ))

    doc.build(story)
    return buffer.getvalue()