from __future__ import annotations

from io import BytesIO
from textwrap import wrap

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .models import Threat


class ThreatSummaryPDF:
    def build(self, filename: str, threats: list[Threat]) -> bytes:
        out = BytesIO()
        c = canvas.Canvas(out, pagesize=A4)
        width, height = A4
        y = height - 20 * mm

        def write_line(text: str, size: int = 10, bold: bool = False, gap: float = 5 * mm):
            nonlocal y
            if y < 20 * mm:
                c.showPage()
                y = height - 20 * mm
            c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            for line in wrap(text, 100):
                c.drawString(15 * mm, y, line)
                y -= 4.5 * mm
            y -= gap - 4.5 * mm

        write_line("FlightBrief AI - Threat Summary", 16, True, 8 * mm)
        write_line(f"Source file: {filename}", 10, False, 6 * mm)

        for priority in ["P1", "P2", "P3"]:
            subset = [t for t in threats if t.priority == priority]
            write_line(f"{priority}", 13, True, 4 * mm)
            if not subset:
                write_line("Nil", 10, False, 4 * mm)
                continue
            for idx, t in enumerate(subset, start=1):
                write_line(f"{idx}. {t.title}", 11, True, 1 * mm)
                write_line(f"Category: {t.category} | Source: {t.source_section} | Page: {t.page_number}", 9)
                write_line(f"Highlight: {t.highlight_text}", 9)
                write_line(f"Why it matters: {t.why_it_matters}", 9)
                write_line(f"Expected crew action: {t.expected_crew_action}", 9, False, 5 * mm)

        c.save()
        return out.getvalue()
