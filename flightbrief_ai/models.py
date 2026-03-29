from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Priority = Literal["P1", "P2", "P3"]


@dataclass
class Threat:
    priority: Priority
    category: str
    title: str
    source_section: str
    highlight_text: str
    why_it_matters: str
    expected_crew_action: str
    affected_phase: str
    affected_area: str
    page_number: int
