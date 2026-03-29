from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .models import Threat


NEGATIVE_PATTERNS = [
    r"\bNO RAIM OUTAGES\b",
    r"\bNO OUTAGES\b",
    r"\bNIL\b",
    r"\bNO WX DATA AVAILABLE\b",
]

RELEVANT_AIRPORTS = {
    "FNLU", "LPPT", "LPFR", "LEZL", "LEMG", "DGAA", "DAAT"
}


def _lines(text: str) -> Iterable[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _is_negative_line(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in NEGATIVE_PATTERNS)


def _extract_airports(line: str) -> list[str]:
    return re.findall(r"\b[A-Z]{4}\b", line)


def _contains_relevant_airport(line: str) -> bool:
    airports = _extract_airports(line)
    return any(ap in RELEVANT_AIRPORTS for ap in airports)


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _make_key(priority: str, category: str, title: str, area: str) -> tuple[str, str, str, str]:
    return (priority, category, title.lower(), area.lower())


def detect_threats(pages: list[dict]) -> list[Threat]:
    raw_threats: list[Threat] = []

    for page in pages:
        pnum = page["page_number"]
        text = page["text"]
        lines = list(_lines(text))
        full_lower = text.lower()

        # --------------------------------------------------
        # MEL / CDL
        # --------------------------------------------------
        mel_lines = []
        if "mel/cdl description" in full_lower or "addt fuel due to mel" in full_lower:
            for line in lines:
                if _is_negative_line(line):
                    continue
                if "ADDT FUEL DUE TO MEL" in line or re.search(r"^[A-Z]-\d{2}-\d{2}", line):
                    mel_lines.append(line)

        if mel_lines:
            highlight = " | ".join(mel_lines[:2])
            raw_threats.append(
                Threat(
                    priority="P2",
                    category="MEL_CDL",
                    title="MEL/CDL item with operational impact",
                    source_section="Operational Flight Plan",
                    highlight_text=highlight,
                    why_it_matters="Há um item MEL/CDL ativo com impacto operacional e/ou de combustível, que deve entrar no briefing.",
                    expected_crew_action="Rever limitações, penalizações e implicações operacionais associadas ao item MEL/CDL.",
                    affected_phase="General",
                    affected_area="General",
                    page_number=pnum,
                )
            )

        # --------------------------------------------------
        # Callsign with appended letter
        # --------------------------------------------------
        m = re.search(r"\(FPL-([A-Z]+\d+[A-Z])-IS", text)
        if m:
            callsign = m.group(1)
            if re.search(r"\d+[A-Z]$", callsign):
                raw_threats.append(
                    Threat(
                        priority="P3",
                        category="CALLSIGN",
                        title="Callsign with appended letter",
                        source_section="ATC Flight Plan",
                        highlight_text=callsign,
                        why_it_matters="Callsign com letra appended aumenta a necessidade de disciplina nas comunicações.",
                        expected_crew_action="Reforçar atenção a listening e readback discipline.",
                        affected_phase="General",
                        affected_area="General",
                        page_number=pnum,
                    )
                )

        # --------------------------------------------------
        # ETOPS / en-route alternate awareness
        # --------------------------------------------------
        etops_lines = [
            ln for ln in lines
            if any(tok in ln.lower() for tok in ["entry1", "etp1", "exit1", "enrte altns", "ralt/"])
        ]
        if etops_lines:
            raw_threats.append(
                Threat(
                    priority="P3",
                    category="ALT_ETOPS",
                    title="ETOPS / en-route alternate awareness",
                    source_section="ETOPS Summary / ATC Flight Plan",
                    highlight_text=etops_lines[0],
                    why_it_matters="A estrutura de entry/ETP/exit e alternantes en-route deve entrar no briefing como awareness.",
                    expected_crew_action="Brief curto sobre alternantes en-route, ETP e lógica de desvio.",
                    affected_phase="Enroute",
                    affected_area="Enroute",
                    page_number=pnum,
                )
            )

        # --------------------------------------------------
        # Weather / advisory
        # --------------------------------------------------
        for line in lines:
            if _is_negative_line(line):
                continue

            lower = line.lower()

            # GNSS / RAIM only if real degradation
            if (
                ("gnss" in lower or "raim" in lower or "rnp 0.1" in lower)
                and not re.search(r"\bno raim outages\b|\bno outages\b", line, re.IGNORECASE)
                and re.search(r"outage|interference|degrad|sev|affected", lower)
            ):
                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="NAV",
                        title="Navigation capability limitation",
                        source_section="RAIM / NOTAM / Advisory",
                        highlight_text=line,
                        why_it_matters="Uma limitação de navegação pode afetar procedimentos ou a lógica de desvio.",
                        expected_crew_action="Rever impacto nos procedimentos e alternantes relevantes.",
                        affected_phase="Enroute",
                        affected_area="General",
                        page_number=pnum,
                    )
                )

            # Convective weather
            elif re.search(r"\btsra\b|\bvcts\b|\bcb\b|\bthunderstorm\b|\bembd ts\b", lower):
                area = "General"
                if "lppt" in lower:
                    area = "LPPT"
                elif "daat" in lower:
                    area = "DAAT"
                elif "fnlu" in lower:
                    area = "FNLU"

                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="MET",
                        title="Convective activity / thunderstorms",
                        source_section="Weather List / SIGMET",
                        highlight_text=line,
                        why_it_matters="Atividade convectiva aumenta workload, desvios táticos e risco de turbulência/precipitação forte.",
                        expected_crew_action="Briefar weather avoidance e monitorização radar/ATC.",
                        affected_phase="Departure" if area == "FNLU" else "General",
                        affected_area=area,
                        page_number=pnum,
                    )
                )

            # Gusty wind
            elif re.search(r"g\d{2,3}kt|gust", lower):
                if _contains_relevant_airport(line) or "lppt" in lower or "daat" in lower or "lpfr" in lower:
                    area = "General"
                    if "lppt" in lower:
                        area = "LPPT"
                    elif "lpfr" in lower:
                        area = "LPFR"
                    elif "daat" in lower:
                        area = "DAAT"

                    raw_threats.append(
                        Threat(
                            priority="P2",
                            category="MET",
                            title="Strong gusty wind",
                            source_section="Weather List",
                            highlight_text=line,
                            why_it_matters="Rajadas fortes podem afetar a fase de aproximação/aterragem ou descolagem.",
                            expected_crew_action="Confirmar runway expectation e estratégia para vento rajado.",
                            affected_phase="Arrival",
                            affected_area=area,
                            page_number=pnum,
                        )
                    )

            # RFF
            elif "rffs" in lower or "fire fighting" in lower:
                if _contains_relevant_airport(line):
                    raw_threats.append(
                        Threat(
                            priority="P2",
                            category="AERODROME",
                            title="RFF downgraded",
                            source_section="NOTAM / Dispatch",
                            highlight_text=line,
                            why_it_matters="Downgrade de RFF num aeródromo relevante para desvio deve entrar no briefing.",
                            expected_crew_action="Confirmar adequacy do aeródromo para eventual desvio.",
                            affected_phase="Diversion",
                            affected_area="Alternate/Enroute alternate",
                            page_number=pnum,
                        )
                    )

        # --------------------------------------------------
        # Procedure cancellations / closures
        # Only relevant aerodromes
        # --------------------------------------------------
        for line in lines:
            if _is_negative_line(line):
                continue

            lower = line.lower()
            if not _contains_relevant_airport(line) and not any(
                ap.lower() in lower for ap in ["fnlu", "lppt", "lpfr", "lezl", "lemg", "daat", "dgaa"]
            ):
                continue

            if (
                re.search(r"closed|closure|canceled|cancelled|u/s|unserviceable", lower)
                and any(x in lower for x in ["runway", "rwy", "taxiway", "vor", "ils", "procedure", "dme", "light"])
            ):
                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="NOTAM_ADX",
                        title="Runway / procedure / navaid limitation",
                        source_section="NOTAM Information",
                        highlight_text=line,
                        why_it_matters="Uma limitação de pista, procedimento ou ajuda rádio pode ser operacionalmente relevante para departure/arrival/diversion.",
                        expected_crew_action="Confirmar procedimento disponível e ajustar o briefing se aplicável.",
                        affected_phase="General",
                        affected_area="Relevant aerodrome",
                        page_number=pnum,
                    )
                )

        # --------------------------------------------------
        # Tropopause proximity: only if within ±5000 ft
        # --------------------------------------------------
        if "w/v trop" in full_lower:
            for line in lines:
                if "W/V TROP" not in line and "w/v trop" not in line.lower():
                    continue

                fl_match = re.search(r"\b(3[2-9]0|400)\b", line)
                trop_match = re.search(r"\|\s*\d{1,2}/\d{3}\s+(\d{2})\|", line)

                if not fl_match or not trop_match:
                    continue

                aircraft_fl = int(fl_match.group(1))        # ex: 390
                trop_fl = int(trop_match.group(1)) * 10     # ex: 39 -> 390, 52 -> 520

                if abs((trop_fl - aircraft_fl) * 100) <= 5000:
                    raw_threats.append(
                        Threat(
                            priority="P2",
                            category="MET",
                            title="Tropopause proximity / CAT awareness",
                            source_section="Operational Flight Plan",
                            highlight_text=line.strip(),
                            why_it_matters="Nível de voo próximo da tropopause pode aumentar o risco de clear air turbulence.",
                            expected_crew_action="Antecipar possível CAT e gerir awareness de cabine e seat belts.",
                            affected_phase="Enroute",
                            affected_area="Cruise",
                            page_number=pnum,
                        )
                    )
                    break

    # --------------------------------------------------
    # Deduplicate / consolidate
    # --------------------------------------------------
    grouped: dict[tuple[str, str, str, str], list[Threat]] = defaultdict(list)
    for threat in raw_threats:
        key = _make_key(threat.priority, threat.category, threat.title, threat.affected_area)
        grouped[key].append(threat)

    final_threats: list[Threat] = []
    for _, group in grouped.items():
        group = sorted(group, key=lambda t: t.page_number)
        first = group[0]

        highlights = []
        seen_h = set()
        for item in group:
            norm = _normalize_text(item.highlight_text)
            if norm not in seen_h:
                seen_h.add(norm)
                highlights.append(item.highlight_text)

        merged_highlight = " | ".join(highlights[:3])

        final_threats.append(
            Threat(
                priority=first.priority,
                category=first.category,
                title=first.title,
                source_section=first.source_section,
                highlight_text=merged_highlight,
                why_it_matters=first.why_it_matters,
                expected_crew_action=first.expected_crew_action,
                affected_phase=first.affected_phase,
                affected_area=first.affected_area,
                page_number=first.page_number,
            )
        )

    order = {"P1": 0, "P2": 1, "P3": 2}
    final_threats.sort(key=lambda t: (order[t.priority], t.page_number, t.title))
    return final_threats
