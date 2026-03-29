from __future__ import annotations

import streamlit as st

from .engine import FlightBriefEngine
from .pdf_annotator import PDFAnnotator
from .summary_pdf import ThreatSummaryPDF


def run_app() -> None:
    st.set_page_config(page_title="FlightBrief AI", layout="wide")
    st.title("FlightBrief AI")
    st.write("Carrega um plano de voo em PDF e obtém dois PDFs: o briefing anotado e o threat summary.")

    uploaded = st.file_uploader("Plano de voo (PDF)", type=["pdf"])
    if uploaded is None:
        st.stop()

    if st.button("Analyze"):
        pdf_bytes = uploaded.read()
        engine = FlightBriefEngine()
        threats = engine.analyze(pdf_bytes)

        st.subheader("Resumo")
        c1, c2, c3 = st.columns(3)
        c1.metric("P1", sum(1 for t in threats if t.priority == "P1"))
        c2.metric("P2", sum(1 for t in threats if t.priority == "P2"))
        c3.metric("P3", sum(1 for t in threats if t.priority == "P3"))

        if threats:
            for t in threats:
                with st.expander(f"{t.priority} · {t.title} · p.{t.page_number}"):
                    st.write(f"**Category:** {t.category}")
                    st.write(f"**Source:** {t.source_section}")
                    st.write(f"**Highlight:** {t.highlight_text}")
                    st.write(f"**Why it matters:** {t.why_it_matters}")
                    st.write(f"**Expected crew action:** {t.expected_crew_action}")
        else:
            st.info("Nenhuma ameaça foi identificada pelas regras atuais.")

        annotated = PDFAnnotator().annotate(pdf_bytes, threats)
        summary = ThreatSummaryPDF().build(uploaded.name, threats)

        st.download_button(
            "Descarregar PDF anotado",
            data=annotated,
            file_name=uploaded.name.replace('.pdf', '_highlighted.pdf'),
            mime="application/pdf",
        )
        st.download_button(
            "Descarregar threat summary PDF",
            data=summary,
            file_name=uploaded.name.replace('.pdf', '_threat_summary.pdf'),
            mime="application/pdf",
        )
