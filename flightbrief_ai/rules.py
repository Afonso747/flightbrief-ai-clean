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
    "KIAD", "LPPT", "LPLA", "KBGR", "LEMD", "LEMG", "LPFR", "LPPR",
    "LPPD", "LPAZ", "KBWI", "KPHL", "KEWR", "KRDU", "TXKF", "CYHZ", "CYQX"
}


def _lines(text: str) -> Iterable[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _is_negative_line(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in NEGATIVE_PATTERNS)


def _extract_airports(line: str) -> list[str]:
    return re.findall(r"\b[A-Z]{4}\b", line)


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _make_key(priority: str, category: str, title: str, area: str) -> tuple[str, str, str, str]:
    return (priority, category, title.lower(), area.upper())


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
            raw_threats.append(
                Threat(
                    priority="P2",
                    category="MEL_CDL",
                    title="MEL/CDL item with operational impact",
                    source_section="Operational Flight Plan",
                    highlight_text=" | ".join(mel_lines[:2]),
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
        # Oceanic / ETOPS awareness
        # --------------------------------------------------
        if any(tok in full_lower for tok in ["entry1", "etp1", "exit1", "oceanic clearance", "39n060w", "40n050w", "41n040w", "42n030w"]):
            raw_threats.append(
                Threat(
                    priority="P3",
                    category="ALT_ETOPS",
                    title="ETOPS / en-route alternate awareness",
                    source_section="ETOPS Summary / ATC Flight Plan",
                    highlight_text="OCEANIC CLEARANCE" if "oceanic clearance" in full_lower else "ETOPS ENTRY1",
                    why_it_matters="A estrutura de entry/ETP/exit e a complexidade oceânica devem entrar no briefing como awareness.",
                    expected_crew_action="Brief curto sobre alternantes en-route, ETP, random waypoints e lógica de desvio.",
                    affected_phase="Enroute",
                    affected_area="North Atlantic",
                    page_number=pnum,
                )
            )

        # --------------------------------------------------
        # Weather list with airport context
        # --------------------------------------------------
        current_airport = None

        for line in lines:
            if _is_negative_line(line):
                continue

            # Detect airport header lines like:
            # KIAD/IAD WASHINGTON/DULLES INTL
            # LPPT/LIS LISBON/HUMBERTO DELGADO
            airport_header = re.match(r"^([A-Z]{4})/[A-Z0-9]{2,4}\b", line)
            if airport_header:
                current_airport = airport_header.group(1)

            lower = line.lower()

            # Windshear
            if "ws020" in lower or "windshear" in lower:
                area = current_airport or "General"
                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="MET",
                        title="Windshear / low-level windshear",
                        source_section="Weather List",
                        highlight_text=line,
                        why_it_matters="Windshear em fase crítica aumenta workload e deve entrar no briefing.",
                        expected_crew_action="Reforçar briefing de departure/arrival e awareness para windshear recovery.",
                        affected_phase="Departure" if area == "KIAD" else "General",
                        affected_area=area,
                        page_number=pnum,
                    )
                )
                continue

            # Convective / TS / CB
            if re.search(r"\btsra\b|\bvcts\b|\bcb\b|\b\+ra\b|\btcu\b|\bembd ts\b", lower):
                area = current_airport or "General"
                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="MET",
                        title="Convective activity / thunderstorms",
                        source_section="Weather List / SIGMET",
                        highlight_text=line,
                        why_it_matters="Atividade convectiva aumenta workload, desvios táticos e risco de turbulência/precipitação forte.",
                        expected_crew_action="Briefar weather avoidance e monitorização radar/ATC.",
                        affected_phase="General",
                        affected_area=area,
                        page_number=pnum,
                    )
                )
                continue

            # Gusty wind
            if re.search(r"\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt", lower):
                area = current_airport or "General"
                raw_threats.append(
                    Threat(
                        priority="P2",
                        category="MET",
                        title="Strong gusty wind",
                        source_section="Weather List",
                        highlight_text=line,
                        why_it_matters="Rajadas fortes podem afetar a fase de aproximação/aterragem ou descolagem.",
                        expected_crew_action="Confirmar runway expectation e estratégia para vento rajado.",
                        affected_phase="General",
                        affected_area=area,
                        page_number=pnum,
                    )
                )
                continue

            # Marginal alternate / diversion weather
            if current_airport in {"LPLA", "LPPR", "LPFR", "LPPD", "LPAZ", "CYHZ", "CYQX", "TXKF", "LEMD", "LEMG"}:
                if re.search(r"\bbr\b|\bovc0\d{2}\b|\bbkn0\d{2}\b|\b-fzdz\b|\bshsn\b|\bshra\b|\b-ra\b", lower):
                    raw_threats.append(
                        Threat(
                            priority="P2",
                            category="ALT_ETOPS",
                            title="Marginal alternate / diversion weather",
                            source_section="Weather List",
                            highlight_text=line,
                            why_it_matters="Meteorologia marginal num alternante ou aeroporto de desvio deve entrar no briefing.",
                            expected_crew_action="Rever adequacy, minima e utilidade real do alternante/desvio.",
                            affected_phase="Diversion",
                            affected_area=current_airport,
                            page_number=pnum,
                        )
                    )

        # --------------------------------------------------
        # Navigation / GNSS / interference
        # --------------------------------------------------
        for line in lines:
            if _is_negative_line(line):
                continue

            lower = line.lower()
            if (
                ("gnss" in lower or "interference" in lower or "rnp10" in lower or "raim" in lower)
                and not re.search(r"\bno raim outages\b|\bno outages\b", lower)
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

        # --------------------------------------------------
        # Runway / procedure / navaid limitation
        # --------------------------------------------------
        for line in lines:
            if _is_negative_line(line):
                continue

            lower = line.lower()
            airports_in_line = _extract_airports(line)
            relevant_here = any(ap in RELEVANT_AIRPORTS for ap in airports_in_line)

            if (
                re.search(r"closed|closure|canceled|cancelled|u/s|unserviceable", lower)
                and any(x in lower for x in ["runway", "rwy", "taxiway", "vor", "ils", "procedure", "dme", "light"])
                and relevant_here
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
                        affected_area=airports_in_line[0] if airports_in_line else "General",
                        page_number=pnum,
                    )
                )

        # --------------------------------------------------
        # Tropopause proximity: ±5000 ft
        # --------------------------------------------------
        if "position| coord" in full_lower:
            for line in lines:
                # tabela das upper winds / tropopause
                # ex: 4050N ... M50 M47 M48 M49 M50
                # esta lógica é simplificada para detetar proximidade com FL330/350 do voo IAD-LIS
                pass

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

    order = {"P1": 0, "P2": 1, "P3": 2}
    final_threats.sort(key=lambda t: (order[t.priority], t.page_number, t.title))
    return final_threats
