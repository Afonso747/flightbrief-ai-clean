from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from .models import Threat


class ThreatSummaryPDF:
    def build(self, filename: str, threats: list[Threat]) -> bytes:
        out = BytesIO()

        doc = SimpleDocTemplate(
            out,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = styles["Title"]
        heading_style = styles["Heading2"]
        normal_style = styles["BodyText"]

        small_style = ParagraphStyle(
            "Small",
            parent=normal_style,
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            spaceAfter=2 * mm,
        )

        item_title_style = ParagraphStyle(
            "ItemTitle",
            parent=normal_style,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            textColor=colors.black,
            spaceAfter=1 * mm,
        )

        story = []
        story.append(Paragraph("FlightBrief AI - Threat Summary", title_style))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(f"Source file: {filename}", small_style))
        story.append(Spacer(1, 6 * mm))

        priority_order = ["P1", "P2", "P3"]

        for idx_priority, priority in enumerate(priority_order):
            subset = [t for t in threats if t.priority == priority]

            story.append(Paragraph(priority, heading_style))
            story.append(Spacer(1, 2 * mm))

            if not subset:
                story.append(Paragraph("Nil", normal_style))
                story.append(Spacer(1, 4 * mm))
            else:
                for idx, t in enumerate(subset, start=1):
                    display_title = t.title
                    if t.affected_area and t.affected_area != "General":
                        display_title = f"{t.title} — {t.affected_area}"

                    story.append(Paragraph(f"{idx}. {display_title}", item_title_style))
                    story.append(
                        Paragraph(
                            f"<b>Category:</b> {t.category} &nbsp;&nbsp; <b>Source:</b> {t.source_section} &nbsp;&nbsp; <b>Page:</b> {t.page_number}",
                            small_style,
                        )
                    )
                    story.append(Paragraph(f"<b>Highlight:</b> {t.highlight_text}", small_style))
                    story.append(Paragraph(f"<b>Why it matters:</b> {t.why_it_matters}", small_style))
                    story.append(Paragraph(f"<b>Expected crew action:</b> {t.expected_crew_action}", small_style))
                    story.append(Spacer(1, 4 * mm))

            if idx_priority < len(priority_order) - 1:
                story.append(Spacer(1, 4 * mm))

        doc.build(story)
        return out.getvalue()
