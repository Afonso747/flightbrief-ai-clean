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
    "LPPD", "LPAZ", "KBWI", "KPHL", "KEWR", "KRDU", "TXKF", "CYHZ", "CYQX",
    "FNLU", "DGAA", "DAAT"
}

ALTERNATE_LIKE_AIRPORTS = {
    "LPLA", "LPPR", "LPFR", "LPPD", "LPAZ", "CYHZ", "CYQX", "TXKF",
    "LEMD", "LEMG", "KBGR", "DGAA", "DAAT"
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


def _hhmm_to_minutes(hhmm: str) -> int:
    hh = int(hhmm[:2])
    mm = int(hhmm[2:])
    return hh * 60 + mm


def _extract_flight_window(pages: list[dict]) -> tuple[int | None, int | None]:
    joined = "\n".join(page["text"] for page in pages[:10])

    etd_match = re.search(r"\bETD\s+(\d{4})\b", joined)
    eta_match = re.search(r"\bETA\s+(\d{4})\b", joined)

    if etd_match and eta_match:
        start = _hhmm_to_minutes(etd_match.group(1))
        end = _hhmm_to_minutes(eta_match.group(1))
        if end < start:
            end += 24 * 60
        end += 120
        return start, end

    cover_match = re.search(
        r"\b[A-Z]{3}\s+(\d{2}:\d{2}).*?\b[A-Z]{3}\s+(\d{2}:\d{2})",
        joined,
        re.DOTALL,
    )
    if cover_match:
        etd = cover_match.group(1).replace(":", "")
        eta = cover_match.group(2).replace(":", "")
        start = _hhmm_to_minutes(etd)
        end = _hhmm_to_minutes(eta)
        if end < start:
            end += 24 * 60
        end += 120
        return start, end

    return None, None


def _time_overlap_minutes(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _align_window_to_flight(start: int, end: int, flight_start: int, flight_end: int) -> tuple[int, int]:
    if end < start:
        end += 24 * 60
    if start < flight_start - 12 * 60:
        start += 24 * 60
        end += 24 * 60
    return start, end


def _parse_taf_group_window(line: str) -> tuple[int | None, int | None]:
    m = re.search(r"\bPROB\d{2}\s+TEMPO\s+(\d{4})/(\d{4})\b", line)
    if m:
        return _hhmm_to_minutes(m.group(1)[-4:]), _hhmm_to_minutes(m.group(2)[-4:])

    m = re.search(r"\bTEMPO\s+(\d{4})/(\d{4})\b", line)
    if m:
        return _hhmm_to_minutes(m.group(1)[-4:]), _hhmm_to_minutes(m.group(2)[-4:])

    m = re.search(r"\bBECMG\s+(\d{4})/(\d{4})\b", line)
    if m:
        return _hhmm_to_minutes(m.group(1)[-4:]), _hhmm_to_minutes(m.group(2)[-4:])

    m = re.search(r"\bFM(\d{6})\b", line)
    if m:
        start = _hhmm_to_minutes(m.group(1)[-4:])
        return start, start + 360

    m = re.search(r"\bFT\s+\d{6}\s+(\d{4})/(\d{4})\b", line)
    if m:
        return _hhmm_to_minutes(m.group(1)[-4:]), _hhmm_to_minutes(m.group(2)[-4:])

    return None, None


def _line_has_weather_threat(line: str) -> bool:
    lower = line.lower()
    return bool(
        re.search(
            r"\btsra\b|\bvcts\b|\bcb\b|\btcu\b|\b\+ra\b|\b-fzdz\b|\bshsn\b|\bshra\b|\b-ra\b|\bbr\b|\bovc0\d{2}\b|\bbkn0\d{2}\b|\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt|ws020|windshear",
            lower,
        )
    )


def _classify_weather_line(line: str, airport: str) -> tuple[str, str, str, str, str]:
    lower = line.lower()

    if "ws020" in lower or "windshear" in lower:
        return (
            "P2",
            "MET",
            "Windshear / low-level windshear",
            f"Windshear em {airport} dentro da janela operacional do voo aumenta workload e deve entrar no briefing.",
            "Reforçar briefing de departure/arrival e awareness para windshear recovery.",
        )

    if re.search(r"\btsra\b|\bvcts\b|\bcb\b|\btcu\b|\b\+ra\b", lower):
        return (
            "P2",
            "MET",
            "Convective activity / thunderstorms",
            f"Atividade convectiva prevista em {airport} dentro da janela operacional do voo aumenta workload, desvios táticos e risco de turbulência/precipitação forte.",
            "Briefar weather avoidance e monitorização radar/ATC.",
        )

    if re.search(r"\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt", lower):
        return (
            "P2",
            "MET",
            "Strong gusty wind",
            f"Rajadas fortes previstas em {airport} dentro da janela operacional do voo podem afetar a fase de aproximação/aterragem ou descolagem.",
            "Confirmar runway expectation e estratégia para vento rajado.",
        )

    if airport in ALTERNATE_LIKE_AIRPORTS and re.search(r"\bbr\b|\bovc0\d{2}\b|\bbkn0\d{2}\b|\b-fzdz\b|\bshsn\b|\bshra\b|\b-ra\b|\bsn\b", lower):
        return (
            "P2",
            "ALT_ETOPS",
            "Marginal alternate / diversion weather",
            f"Meteorologia marginal em {airport}, relevante dentro da janela operacional do voo, deve entrar no briefing como opção de alternante/desvio.",
            "Rever adequacy, minima e utilidade real do alternante/desvio.",
        )

    return (
        "P2",
        "MET",
        "Weather awareness",
        f"Condição meteorológica relevante em {airport} dentro da janela operacional do voo.",
        "Rever impacto operacional e incluir no briefing se aplicável.",
    )


def _build_airport_weather_blocks(lines: list[str]) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = defaultdict(list)
    current_airport = None

    for line in lines:
        header = re.match(r"^([A-Z]{4})/[A-Z0-9]{2,4}\b", line)
        if header:
            current_airport = header.group(1)
            continue

        if current_airport:
            blocks[current_airport].append(line)

    return dict(blocks)


def _extract_weather_threats_from_airport_block(
    airport: str,
    lines: list[str],
    page_number: int,
    window_start: int | None,
    window_end: int | None,
) -> list[Threat]:
    threats: list[Threat] = []

    if window_start is None or window_end is None:
        return threats

    for line in lines:
        if _is_negative_line(line):
            continue
        if not _line_has_weather_threat(line):
            continue

        start, end = _parse_taf_group_window(line)

        if start is None or end is None:
            if line.startswith("SA "):
                start = window_start
                end = window_end
            else:
                continue

        start, end = _align_window_to_flight(start, end, window_start, window_end)

        if not _time_overlap_minutes(start, end, window_start, window_end):
            continue

        priority, category, title, why, expected_action = _classify_weather_line(line, airport)

        affected_phase = "General"
        if airport in {"KIAD", "FNLU"} and ("ws020" in line.lower() or "windshear" in line.lower()):
            affected_phase = "Departure"
        elif airport == "LPPT":
            affected_phase = "Arrival"
        elif airport in ALTERNATE_LIKE_AIRPORTS:
            affected_phase = "Diversion"

        threats.append(
            Threat(
                priority=priority,
                category=category,
                title=title,
                source_section="Weather List",
                highlight_text=line,
                why_it_matters=why,
                expected_crew_action=expected_action,
                affected_phase=affected_phase,
                affected_area=airport,
                page_number=page_number,
            )
        )

    return threats


def detect_threats(pages: list[dict]) -> list[Threat]:
    raw_threats: list[Threat] = []
    window_start, window_end = _extract_flight_window(pages)

    for page in pages:
        pnum = page["page_number"]
        text = page["text"]
        lines = list(_lines(text))
        full_lower = text.lower()

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

        if "airport weather list" in full_lower or "destination:" in full_lower or "departure:" in full_lower:
            airport_blocks = _build_airport_weather_blocks(lines)
            for airport, airport_lines in airport_blocks.items():
                raw_threats.extend(
                    _extract_weather_threats_from_airport_block(
                        airport=airport,
                        lines=airport_lines,
                        page_number=pnum,
                        window_start=window_start,
                        window_end=window_end,
                    )
                )

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
