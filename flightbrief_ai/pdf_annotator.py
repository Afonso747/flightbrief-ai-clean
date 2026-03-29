from __future__ import annotations

from io import BytesIO

import fitz

from .models import Threat


class PDFAnnotator:
    def annotate(self, pdf_bytes: bytes, threats: list[Threat]) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        by_page: dict[int, list[Threat]] = {}
        for t in threats:
            by_page.setdefault(t.page_number, []).append(t)

        for pnum, page_threats in by_page.items():
            page = doc[pnum - 1]
            for threat in page_threats:
                text = threat.highlight_text.strip()
                if not text:
                    continue
                rects = page.search_for(text)
                if not rects and len(text) > 80:
                    rects = page.search_for(text[:80])
                if not rects and len(text.split()) > 3:
                    rects = page.search_for(" ".join(text.split()[:4]))
                for rect in rects[:3]:
                    annot = page.add_highlight_annot(rect)
                    annot.set_info(title="FlightBrief AI", content=f"{threat.priority} · {threat.title}")
                    annot.update()
        output = BytesIO()
        doc.save(output)
        doc.close()
        return output.getvalue()
