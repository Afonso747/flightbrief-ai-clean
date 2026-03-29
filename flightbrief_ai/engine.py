from __future__ import annotations

from .parsing import extract_pages
from .rules import detect_threats


class FlightBriefEngine:
    def analyze(self, pdf_bytes: bytes):
        pages = extract_pages(pdf_bytes)
        threats = detect_threats(pages)
        return threats
