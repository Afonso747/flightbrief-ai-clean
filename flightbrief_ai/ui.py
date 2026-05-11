from __future__ import annotations

import hashlib
import re

import fitz  # PyMuPDF
import streamlit as st

from flightbrief_ai.engine import FlightBriefEngine
from flightbrief_ai.feedback_store import save_feedback
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
        "threats": [],
        "feedback_submitted": set(),
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
    st.session_state["threats"] = []
    st.session_state["feedback_submitted"] = set()


@st.cache_data(show_spinner=False)
def _render_pdf_pages(pdf_bytes: bytes) -> list[bytes]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images: list[bytes] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.15, 1.15), alpha=False)
        images.append(pix.tobytes("png"))

    doc.close()
    return images


def _extract_flight_context_from_pdf(pdf_bytes: bytes) -> dict[str, str]:
    context = {
        "callsign": "",
        "departure": "",
        "destination": "",
        "aircraft_type": "",
        "flight_date": "",
    }

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for i in range(min(3, len(doc))):
            text += "\n" + doc.load_page(i).get_text("text")
        doc.close()

        m = re.search(
            r"\b([A-Z]{3}\d{1,4})\s+(\d{2}[A-Z]{3}\d{4})\s+([A-Z]{4})\s+([A-Z]{4})\s+([A-Z0-9-]+)\b",
            text,
        )
        if m:
            context["callsign"] = m.group(1)
            context["flight_date"] = m.group(2)
            context["departure"] = m.group(3)
            context["destination"] = m.group(4)
            context["aircraft_type"] = m.group(5)
            return context

        m2 = re.search(r"\b(A339|A21N|A321|A330)\b", text)
        if m2:
            context["aircraft_type"] = m2.group(1)

    except Exception:
        pass

    return context


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


def _render_feedback_for_threats(flight_context: dict[str, str]) -> None:
    threats = st.session_state.get("threats", [])
    if not threats:
        return

    st.divider()
    st.subheader("Threat feedback")
    st.write("Classifica cada threat para a app começar a aprender o que realmente interessa.")

    for idx, threat in enumerate(threats):
        title = getattr(threat, "title", "Untitled threat")
        priority = getattr(threat, "priority", "-")
        area = getattr(threat, "affected_area", "-")
        highlight = getattr(threat, "highlight_text", "-")
        why = getattr(threat, "why_it_matters", "-")

        threat_key = f"{idx}_{title}_{area}_{priority}"

        with st.expander(f"{priority} | {title} | {area}", expanded=False):
            st.markdown(f"**Highlight:** {highlight}")
            st.markdown(f"**Why it matters:** {why}")

            feedback_choice = st.radio(
                "Feedback",
                options=[
                    "Relevant",
                    "Not relevant",
                    "Wrong priority",
                    "Too noisy",
                    "Missed context around this threat",
                ],
                key=f"feedback_choice_{threat_key}",
            )

            notes = st.text_area(
                "Optional notes",
                key=f"feedback_notes_{threat_key}",
                placeholder="Ex.: devia ser P3 e não P2 / alternante irrelevante / boa deteção",
            )

            already_done = threat_key in st.session_state["feedback_submitted"]

            if st.button(
                "Save feedback",
                key=f"feedback_save_{threat_key}",
                disabled=already_done,
                use_container_width=True,
            ):
                save_feedback(
                    flight_context=flight_context,
                    threat=threat,
                    feedback_label=feedback_choice,
                    notes=notes,
                )
                st.session_state["feedback_submitted"].add(threat_key)
                st.success("Feedback guardado.")
                st.rerun()

            if already_done:
                st.info("Feedback já guardado para esta threat.")


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

    flight_context = _extract_flight_context_from_pdf(pdf_bytes)

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
            st.session_state["threats"] = threats
            st.session_state["analysis_done"] = True

    if st.session_state["analysis_done"]:
        st.success("Análise concluída.")

        c1, c2 = st.columns(2)

        with c1:
            st.download_button(
                label="Download highlighted flight plan",
                data=st.session_state["annotated_pdf_bytes"],
                file_name="highlighted_flight_plan.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        with c2:
            st.download_button(
                label="Download threat summary",
                data=st.session_state["summary_pdf_bytes"],
                file_name="threat_summary.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        _render_feedback_for_threats(flight_context)
