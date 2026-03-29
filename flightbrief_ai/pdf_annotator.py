from __future__ import annotations

import re
from io import BytesIO

import fitz  # PyMuPDF

from .models import Threat


SYNTHETIC_HIGHLIGHTS = {
    "Tropopause/FL proximity requires CAT awareness",
}


class PDFAnnotator:
    def annotate(self, pdf_bytes: bytes, threats: list[Threat]) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for threat in threats:
            self._annotate_threat(doc, threat)

        out = BytesIO()
        doc.save(out)
        doc.close()
        return out.getvalue()

    def _annotate_threat(self, doc: fitz.Document, threat: Threat) -> None:
        raw = (threat.highlight_text or "").strip()
        if not raw:
            return

        # split merged highlights
        candidates = [c.strip() for c in raw.split("|") if c.strip()]

        # remove synthetic/non-literal strings
        candidates = [c for c in candidates if c not in SYNTHETIC_HIGHLIGHTS]

        # clean and dedupe
        seen = set()
        cleaned_candidates = []
        for c in candidates:
            c2 = self._clean_candidate(c)
            if c2 and c2 not in seen:
                seen.add(c2)
                cleaned_candidates.append(c2)

        if not cleaned_candidates:
            return

        # first try the page where the threat was detected
        preferred_page_index = max(0, threat.page_number - 1)
        page_order = [preferred_page_index] + [i for i in range(len(doc)) if i != preferred_page_index]

        matched_once = False

        for candidate in cleaned_candidates:
            found_for_candidate = False

            for page_index in page_order:
                page = doc[page_index]

                rects = page.search_for(candidate, quads=False)
                if not rects:
                    # fallback: normalized flexible match
                    rects = self._search_flexible(page, candidate)

                if rects:
                    for rect in rects[:3]:  # avoid excessive repeated highlights
                        annot = page.add_highlight_annot(rect)
                        annot.set_info(
                            content=f"{threat.priority} | {threat.title} | {threat.category}"
                        )
                        annot.update()
                    found_for_candidate = True
                    matched_once = True
                    break

            # if we already found at least one strong match for the threat,
            # don't spray too many highlights around the whole PDF
            if matched_once and found_for_candidate:
                continue

    def _clean_candidate(self, text: str) -> str:
        text = text.strip()

        # remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # ignore too-short generic strings
        if len(text) < 8:
            return ""

        # ignore generic labels that are not useful for highlighting
        generic = {
            "ENTRY1",
            "ETP1",
            "EXIT1",
            "ENRTE ALTNS (WEATHER SUITABILITY PERIOD)",
            "AOI RFFS:",
        }
        if text in generic:
            return ""

        return text

    def _search_flexible(self, page: fitz.Page, candidate: str) -> list[fitz.Rect]:
        """
        Fallback matching for cases where the PDF text spacing/wrapping differs.
        We split long candidates into chunks and try the most informative chunk first.
        """
        chunks = self._candidate_chunks(candidate)

        for chunk in chunks:
            rects = page.search_for(chunk, quads=False)
            if rects:
                return rects

        return []

    def _candidate_chunks(self, text: str) -> list[str]:
        # remove repeated spaces
        text = re.sub(r"\s+", " ", text).strip()

        # if short enough, try as-is
        chunks = [text]

        # split long text by punctuation / keywords
        splitters = [r"\s-\s", r"\s/\s", r",", r";"]
        for splitter in splitters:
            parts = [p.strip() for p in re.split(splitter, text) if p.strip()]
            if len(parts) > 1:
                chunks.extend(parts)

        # also try word windows for very long text
        words = text.split()
        if len(words) > 8:
            chunks.append(" ".join(words[:6]))
            chunks.append(" ".join(words[-6:]))

        # prioritize longer chunks first
        chunks = sorted(set(chunks), key=len, reverse=True)

        # ignore useless tiny chunks
        return [c for c in chunks if len(c) >= 8]
