from __future__ import annotations

import hashlib

import fitz  # PyMuPDF
import streamlit as st

from flightbrief_ai.engine import FlightBriefEngine
from flightbrief_ai.pdf_annotator import PDFAnnotator
from flightbrief_ai.summary_pdf import ThreatSummaryPDF


def _init_review_state() -> None:
    defaults = {
        "review_pdf_name": None,
        "review_pdf_hash": None,
        "review_acknowledged": False,
        "analysis_done": False,
        "annotated_pdf_bytes": None,
        "summary_pdf_bytes": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _reset_review_state_for_new_file(pdf_name: str, pdf_bytes: bytes) -> None:
    st.session_state["review_pdf_name"] = pdf_name
    st.session_state["review_pdf_hash"] = _pdf_hash(pdf_bytes)
    st.session_state["review_acknowledged"] = False
    st.session_state["analysis_done"] = False
    st.session_state["annotated_pdf_bytes"] = None
    st.session_state["summary_pdf_bytes"] = None


@st.cache_data(show_spinner=False)
def _render_pdf_pages(pdf_bytes: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[bytes] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        images.append(pix.tobytes("png"))

    doc.close()
    return images


def _render_review_gate(pdf_bytes: bytes, pdf_name: str) -> bool:
    current_hash = _pdf_hash(pdf_bytes)

    if (
        st.session_state["review_pdf_name"] != pdf_name
        or st.session_state["review_pdf_hash"] != current_hash
    ):
        _reset_review_state_for_new_file(pdf_name, pdf_bytes)

    st.subheader("Mandatory datapackage review")
    st.write(
        "Before analysis, the user must scroll through the entire company-provided datapackage."
    )

    with st.spinner("A preparar visualização do datapackage..."):
        page_images = _render_pdf_pages(pdf_bytes)

    st.info(
        "Scroll to the bottom of the datapackage. The acknowledgement section is only available after the last page."
    )

    for idx, image_bytes in enumerate(page_images, start=1):
        st.image(
            image_bytes,
            caption=f"Page {idx} of {len(page_images)}",
            use_container_width=True,
        )

    st.divider()
    st.success("End of document reached.")

    st.session_state["review_acknowledged"] = st.checkbox(
        "I have read the entire company provided datapackage",
        value=st.session_state["review_acknowledged"],
        key=f"review_ack_{current_hash}",
    )

    return bool(st.session_state["review_acknowledged"])


def run_app() -> None:
    st.set_page_config(page_title="FlightBrief AI", layout="wide")
    _init_review_state()

    st.title("FlightBrief AI")
    st.write(
        "Carrega um plano de voo em PDF, percorre todo o datapackage e obtém dois PDFs: o briefing anotado e o threat summary."
    )

    uploaded_file = st.file_uploader("Carregar plano de voo (PDF)", type=["pdf"])

    if uploaded_file is None:
        return

    pdf_bytes = uploaded_file.read()
    if not pdf_bytes:
        st.error("Não foi possível ler o ficheiro PDF.")
        return

    review_ok = _render_review_gate(pdf_bytes, uploaded_file.name)

    st.divider()
    st.subheader("Analysis")

    if st.button("Analyze flight plan", disabled=not review_ok, type="primary"):
        with st.spinner("A analisar plano de voo..."):
            engine = FlightBriefEngine()
            threats = engine.analyze(pdf_bytes)

            annotator = PDFAnnotator()
            annotated_pdf_bytes = annotator.annotate(pdf_bytes, threats)

            summary_builder = ThreatSummaryPDF()
            summary_pdf_bytes = summary_builder.build(threats)

            st.session_state["annotated_pdf_bytes"] = annotated_pdf_bytes
            st.session_state["summary_pdf_bytes"] = summary_pdf_bytes
            st.session_state["analysis_done"] = True

    if st.session_state["analysis_done"]:
        st.success("Análise concluída.")

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                label="Download highlighted flight plan",
                data=st.session_state["annotated_pdf_bytes"],
                file_name="highlighted_flight_plan.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with col2:
            st.download_button(
                label="Download threat summary",
                data=st.session_state["summary_pdf_bytes"],
                file_name="threat_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
