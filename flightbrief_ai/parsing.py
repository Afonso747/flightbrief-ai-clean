from __future__ import annotations

import fitz


def extract_pages(pdf_bytes: bytes) -> list[dict]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        pages.append({"page_number": i + 1, "text": text})
    doc.close()
    return pages
