from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Paragraph, Table, TableStyle


def _safe(value: Any) -> str:
    if value is None:
        return "-"
    return str(value).strip() if str(value).strip() else "-"


def _priority_sort_key(priority: str) -> int:
    mapping = {"P1": 1, "P2": 2, "P3": 3}
    return mapping.get(priority, 9)


class ThreatSummaryPDF:
    def build(self, threats: list[Any]) -> bytes:
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "title_style",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.black,
            alignment=TA_LEFT,
            spaceAfter=8,
        )

        subtitle_style = ParagraphStyle(
            "subtitle_style",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#444444"),
            spaceAfter=10,
        )

        section_style = ParagraphStyle(
            "section_style",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.black,
            spaceBefore=8,
            spaceAfter=6,
        )

        label_style = ParagraphStyle(
            "label_style",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.black,
        )

        body_style = ParagraphStyle(
            "body_style",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.black,
        )

        small_style = ParagraphStyle(
            "small_style",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#333333"),
        )

        story = []

        story.append(Paragraph("Threat Summary", title_style))
        story.append(
            Paragraph(
                "Automatically generated operational threat review.",
                subtitle_style,
            )
        )

        if not threats:
            story.append(Paragraph("No threats identified.", body_style))
            doc.build(story)
            return buffer.getvalue()

        sorted_threats = sorted(
            threats,
            key=lambda t: (
                _priority_sort_key(_safe(getattr(t, "priority", None))),
                _safe(getattr(t, "page_number", None)),
                _safe(getattr(t, "title", None)),
            ),
        )

        grouped: dict[str, list[Any]] = {}
        for threat in sorted_threats:
            prio = _safe(getattr(threat, "priority", None))
            grouped.setdefault(prio, []).append(threat)

        for priority in ["P1", "P2", "P3"]:
            if priority not in grouped:
                continue

            story.append(Paragraph(priority, section_style))
            story.append(Spacer(1, 2 * mm))

            for threat in grouped[priority]:
                title = _safe(getattr(threat, "title", None))
                category = _safe(getattr(threat, "category", None))
                area = _safe(getattr(threat, "affected_area", None))
                phase = _safe(getattr(threat, "affected_phase", None))
                source = _safe(getattr(threat, "source_section", None))
                page = _safe(getattr(threat, "page_number", None))
                highlight = _safe(getattr(threat, "highlight_text", None))
                why = _safe(getattr(threat, "why_it_matters", None))
                action = _safe(getattr(threat, "expected_crew_action", None))

                block_data = [
                    [
                        Paragraph("<b>Title</b>", label_style),
                        Paragraph(title, body_style),
                    ],
                    [
                        Paragraph("<b>Category</b>", label_style),
                        Paragraph(category, body_style),
                    ],
                    [
                        Paragraph("<b>Affected area</b>", label_style),
                        Paragraph(area, body_style),
                    ],
                    [
                        Paragraph("<b>Phase</b>", label_style),
                        Paragraph(phase, body_style),
                    ],
                    [
                        Paragraph("<b>Source</b>", label_style),
                        Paragraph(f"{source} (page {page})", body_style),
                    ],
                    [
                        Paragraph("<b>Highlight</b>", label_style),
                        Paragraph(highlight, small_style),
                    ],
                    [
                        Paragraph("<b>Why it matters</b>", label_style),
                        Paragraph(why, body_style),
                    ],
                    [
                        Paragraph("<b>Expected crew action</b>", label_style),
                        Paragraph(action, body_style),
                    ],
                ]

                table = Table(
                    block_data,
                    colWidths=[42 * mm, 132 * mm],
                    hAlign="LEFT",
                )

                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#BDBDBD")),
                            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D6D6D6")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F7F7F7")),
                        ]
                    )
                )

                story.append(table)
                story.append(Spacer(1, 4 * mm))

        doc.build(story)
        return buffer.getvalue()
