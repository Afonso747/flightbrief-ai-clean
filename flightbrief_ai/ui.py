from __future__ import annotations

import streamlit as st

from .engine import FlightBriefEngine
from .pdf_annotator import PDFAnnotator
from .summary_pdf import ThreatSummaryPDF


def run_app() -> None:
    st.set_page_config(page_title="FlightBrief AI", layout="wide")

    st.title("FlightBrief AI")
    st.write("Carrega um plano de voo em PDF e obtém dois PDFs: o briefing anotado e o threat summary.")

    uploaded_file = st.file_uploader("Upload flight plan PDF", type=["pdf"])

    if "annotated_pdf_bytes" not in st.session_state:
        st.session_state.annotated_pdf_bytes = None
    if "summary_pdf_bytes" not in st.session_state:
        st.session_state.summary_pdf_bytes = None
    if "source_filename" not in st.session_state:
        st.session_state.source_filename = None
    if "threat_count" not in st.session_state:
        st.session_state.threat_count = 0

    if uploaded_file is not None:
        st.session_state.source_filename = uploaded_file.name

        if st.button("Analyze", type="primary"):
            pdf_bytes = uploaded_file.read()

            engine = FlightBriefEngine()
            threats = engine.analyze(pdf_bytes)

            annotator = PDFAnnotator()
            annotated_pdf = annotator.annotate(pdf_bytes, threats)

            summary_builder = ThreatSummaryPDF()
            summary_pdf = summary_builder.build(uploaded_file.name, threats)

            st.session_state.annotated_pdf_bytes = annotated_pdf
            st.session_state.summary_pdf_bytes = summary_pdf
            st.session_state.threat_count = len(threats)

    if st.session_state.annotated_pdf_bytes or st.session_state.summary_pdf_bytes:
        st.success(f"Analysis complete. Threats found: {st.session_state.threat_count}")

        base_name = (st.session_state.source_filename or "flightplan").replace(".pdf", "")

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                label="Download highlighted flight plan PDF",
                data=st.session_state.annotated_pdf_bytes,
                file_name=f"{base_name}_highlighted.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with col2:
            st.download_button(
                label="Download threat summary PDF",
                data=st.session_state.summary_pdf_bytes,
                file_name=f"{base_name}_threat_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
