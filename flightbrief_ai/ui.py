from __future__ import annotations

import hashlib

import fitz  # PyMuPDF
import streamlit as st

from flightbrief_ai.engine import FlightBriefEngine
from flightbrief_ai.pdf_annotator import PDFAnnotator
from flightbrief_ai.summary_pdf import ThreatSummaryPDF


def _init_state() -> None:
    defaults = {
        "review_pdf_name": None,
        "review_pdf_hash": None,
        "review_completed": False,
        "review_checkbox": False,
        "show_review_dialog": False,
        "analysis_done": False,
        "annotated_pdf_bytes": None,
        "summary_pdf_bytes": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def _reset_state_for_new_file(pdf_name: str, pdf_bytes: bytes) -> None:
    st.session_state["review_pdf_name"] = pdf_name
    st.session_state["review_pdf_hash"] = _pdf_hash(pdf_bytes)
    st.session_state["review_completed"] = False
    st.session_state["review_checkbox"] = False
    st.session_state["show_review_dialog"] = False
    st.session_state["analysis_done"] = False
    st.session_state["annotated_pdf_bytes"] = None
    st.session_state["summary_pdf_bytes"] = None


@st.cache_data(show_spinner=False)
def _render_pdf_pages(pdf_bytes: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[bytes] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False)
        images.append(pix.tobytes("png"))

    doc.close()
    return images


@st.dialog("Mandatory datapackage review", width="large", dismissible=False)
def _review_dialog(pdf_bytes: bytes, pdf_hash: str) -> None:
    st.write(
        "Scroll through the entire company-provided datapackage. "
        "The confirmation checkbox is only available at the end of the review window."
    )

    page_images = _render_pdf_pages(pdf_bytes)

    review_box = st.container(height=650, border=True)
    with review_box:
        st.caption("Scroll to the bottom of this window to continue.")
        for idx, image_bytes in enumerate(page_images, start=1):
            st.image(
                image_bytes,
                caption=f"Page {idx} of {len(page_images)}",
                use_container_width=True,
            )

        st.divider()
        st.success("End of datapackage reached.")

        acknowledged = st.checkbox(
            "I have read the entire company provided datapackage",
            key=f"review_checkbox_{pdf_hash}",
        )

        if acknowledged:
            if st.button("Proceed to analysis", type="primary", use_container_width=True):
                st.session_state["review_completed"] = True
                st.session_state["review_checkbox"] = True
                st.session_state["show_review_dialog"] = False
                st.rerun()


def run_app() -> None:
    st.set_page_config(page_title="FlightBrief AI", layout="wide")
    _init_state()

    st.title("FlightBrief AI")
    st.write(
        "Carrega um plano de voo em PDF, faz a revisão obrigatória do datapackage e obtém dois PDFs: "
        "o briefing anotado e o threat summary."
    )

    uploaded_file = st.file_uploader("Carregar plano de voo (PDF)", type=["pdf"])

    if uploaded_file is None:
        return

    pdf_bytes = uploaded_file.read()
    if not pdf_bytes:
        st.error("Não foi possível ler o ficheiro PDF.")
        return

    current_hash = _pdf_hash(pdf_bytes)
    if (
        st.session_state["review_pdf_name"] != uploaded_file.name
        or st.session_state["review_pdf_hash"] != current_hash
    ):
        _reset_state_for_new_file(uploaded_file.name, pdf_bytes)

    st.subheader("Review status")
    if st.session_state["review_completed"]:
        st.success("Datapackage review completed.")
    else:
        st.warning("Datapackage review pending.")

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("Open mandatory review", type="primary", use_container_width=True):
            st.session_state["show_review_dialog"] = True

    with col2:
        if not st.session_state["review_completed"]:
            st.info("You must complete the mandatory review pop-up before analysis is enabled.")

    if st.session_state["show_review_dialog"]:
        _review_dialog(pdf_bytes, current_hash)

    st.divider()
    st.subheader("Analysis")

    can_analyze = st.session_state["review_completed"]

    if st.button("Analyze flight plan", disabled=not can_analyze, type="primary"):
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
