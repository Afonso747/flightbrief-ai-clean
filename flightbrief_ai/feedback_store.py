from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEEDBACK_DIR = Path("data")
FEEDBACK_FILE = FEEDBACK_DIR / "threat_feedback.jsonl"


def _safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _threat_to_dict(threat: Any) -> dict[str, Any]:
    if is_dataclass(threat):
        raw = asdict(threat)
    else:
        raw = {
            "priority": getattr(threat, "priority", ""),
            "category": getattr(threat, "category", ""),
            "title": getattr(threat, "title", ""),
            "source_section": getattr(threat, "source_section", ""),
            "highlight_text": getattr(threat, "highlight_text", ""),
            "why_it_matters": getattr(threat, "why_it_matters", ""),
            "expected_crew_action": getattr(threat, "expected_crew_action", ""),
            "affected_phase": getattr(threat, "affected_phase", ""),
            "affected_area": getattr(threat, "affected_area", ""),
            "page_number": getattr(threat, "page_number", ""),
        }

    return {k: _safe(v) for k, v in raw.items()}


def save_feedback(
    *,
    flight_context: dict[str, Any],
    threat: Any,
    feedback_label: str,
    notes: str = "",
) -> None:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "flight_context": {k: _safe(v) for k, v in flight_context.items()},
        "threat": _threat_to_dict(threat),
        "feedback_label": _safe(feedback_label),
        "notes": _safe(notes),
    }

    with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
