from __future__ import annotations

import base64
import hashlib
import json

import fitz  # PyMuPDF
import streamlit as st
import streamlit.components.v1 as components

from flightbrief_ai.engine import FlightBriefEngine
from flightbrief_ai.pdf_annotator import PDFAnnotator
from flightbrief_ai.summary_pdf import ThreatSummaryPDF


def _init_review_state() -> None:
    defaults = {
        "review_pdf_name": None,
        "review_pdf_hash": None,
        "review_scrolled_to_end": False,
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
    st.session_state["review_scrolled_to_end"] = False
    st.session_state["review_acknowledged"] = False
    st.session_state["analysis_done"] = False
    st.session_state["annotated_pdf_bytes"] = None
    st.session_state["summary_pdf_bytes"] = None


def _render_pdf_pages_as_base64(pdf_bytes: bytes) -> list[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images_b64: list[str] = []

    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
        img_bytes = pix.tobytes("png")
        images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))

    doc.close()
    return images_b64


def _scroll_review_component(images_b64: list[str], component_key: str) -> bool:
    payload = json.dumps(images_b64)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          font-family: Arial, sans-serif;
          background: white;
        }}
        .wrapper {{
          border: 1px solid #d9d9d9;
          border-radius: 10px;
          overflow: hidden;
        }}
        .header {{
          padding: 10px 12px;
          border-bottom: 1px solid #e6e6e6;
          background: #fafafa;
          font-size: 14px;
        }}
        .viewer {{
          height: 700px;
          overflow-y: auto;
          background: #f3f4f6;
          padding: 16px;
          box-sizing: border-box;
          scroll-behavior: smooth;
        }}
        .page {{
          display: block;
          width: 100%;
          max-width: 900px;
          margin: 0 auto 16px auto;
          background: white;
          box-shadow: 0 1px 4px rgba(0,0,0,0.12);
          border-radius: 6px;
        }}
        .footer {{
          padding: 10px 12px;
          border-top: 1px solid #e6e6e6;
          background: #fafafa;
          font-size: 13px;
        }}
        .ok {{
          color: #0a7f39;
          font-weight: 600;
        }}
        .pending {{
          color: #8a5a00;
          font-weight: 600;
        }}
        .hidden {{
          display: none;
        }}
        .unlock-btn {{
          margin-top: 10px;
          padding: 10px 14px;
          border: 0;
          border-radius: 8px;
          background: #0f62fe;
          color: white;
          font-size: 14px;
          cursor: pointer;
        }}
        .unlock-btn:disabled {{
          background: #9ca3af;
          cursor: not-allowed;
        }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="header">
          Scroll through the entire company datapackage to unlock acknowledgement.
        </div>
        <div id="viewer" class="viewer"></div>
        <div class="footer">
          <div id="status" class="pending">Scroll to the end of the document to continue.</div>
          <button id="unlockBtn" class="unlock-btn hidden">Unlock acknowledgement</button>
        </div>
      </div>

      <script>
        const images = {payload};
        const viewer = document.getElementById("viewer");
        const statusEl = document.getElementById("status");
        const unlockBtn = document.getElementById("unlockBtn");
        let reachedBottom = false;

        images.forEach((img64, idx) => {{
          const img = document.createElement("img");
          img.className = "page";
          img.src = "data:image/png;base64," + img64;
          img.alt = "Page " + (idx + 1);
          viewer.appendChild(img);
        }});

        function sendValue(value) {{
          window.parent.postMessage({{
            isStreamlitMessage: true,
            type: "streamlit:setComponentValue",
            value: value
          }}, "*");
        }}

        function setFrameHeight(height) {{
          window.parent.postMessage({{
            isStreamlitMessage: true,
            type: "streamlit:setFrameHeight",
            height: height
          }}, "*");
        }}

        function checkScroll() {{
          const threshold = 20;
          const atBottom =
            viewer.scrollTop + viewer.clientHeight >= viewer.scrollHeight - threshold;

          if (atBottom && !reachedBottom) {{
            reachedBottom = true;
            statusEl.textContent = "End of document reached. Click below to unlock acknowledgement.";
            statusEl.className = "ok";
            unlockBtn.classList.remove("hidden");
          }}
        }}

        viewer.addEventListener("scroll", checkScroll);

        unlockBtn.addEventListener("click", () => {{
          if (!reachedBottom) return;
          sendValue(true);
        }});

        window.addEventListener("load", () => {{
          setFrameHeight(860);
        }});

        setTimeout(() => setFrameHeight(860), 300);
      </script>
    </body>
    </html>
    """

    value = components.html(html, height=860, scrolling=False)
    return value is True


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
        images_b64 = _render_pdf_pages_as_base64(pdf_bytes)

    unlocked = _scroll_review_component(
        images_b64,
        component_key=f"scroll-review-{current_hash}",
    )

    if unlocked:
        st.session_state["review_scrolled_to_end"] = True

    if st.session_state["review_scrolled_to_end"]:
        st.success("Acknowledgement unlocked.")
        st.session_state["review_acknowledged"] = st.checkbox(
            "I have read the entire company provided datapackage",
            value=st.session_state["review_acknowledged"],
            key=f"review_ack_{current_hash}",
        )
    else:
        st.session_state["review_acknowledged"] = False
        st.warning("You must scroll to the end of the document and unlock acknowledgement before continuing.")

    return bool(
        st.session_state["review_scrolled_to_end"]
        and st.session_state["review_acknowledged"]
    )


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
