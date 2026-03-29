from __future__ import annotations

import re
from typing import Iterable

from .models import Threat


def _lines(text: str) -> Iterable[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _find_matches(lines: Iterable[str], patterns: list[tuple[str, str]]):
    for line in lines:
        lower = line.lower()
        for pattern, tag in patterns:
            if re.search(pattern, lower):
                yield line, tag
                break


def detect_threats(pages: list[dict]) -> list[Threat]:
    threats: list[Threat] = []
    seen: set[tuple[str, int]] = set()

    for page in pages:
        pnum = page["page_number"]
        text = page["text"]
        lines = list(_lines(text))
        full_lower = text.lower()

        # MEL/CDL
        if "mEL/cdl description".lower() in full_lower or "addt fuel due to mel" in full_lower:
            for line in lines:
                if "MEL/CDL DESCRIPTION" in line or "ADDT FUEL DUE TO MEL" in line or re.search(r"^[A-Z]-\d{2}-\d{2}", line):
                    key = (line, pnum)
                    if key in seen:
                        continue
                    seen.add(key)
                    threats.append(Threat(
                        priority="P2",
                        category="MEL_CDL",
                        title="MEL/CDL item with operational impact",
                        source_section="Operational Flight Plan",
                        highlight_text=line,
                        why_it_matters="Há um item MEL/CDL ativo com potencial impacto operacional e/ou de combustível, que deve entrar no briefing.",
                        expected_crew_action="Rever limitações, penalizações e implicações operacionais associadas ao item MEL/CDL.",
                        affected_phase="General",
                        affected_area="General",
                        page_number=pnum,
                    ))

        # Callsign with appended letter
        m = re.search(r"\(FPL-[A-Z]+\d+[A-Z]-IS", text)
        if m:
            callsign = m.group(1).split("-")[1]
            if re.search(r"\d+[A-Z]$", callsign):
                line = callsign
                key = (line, pnum)
                if key not in seen:
                    seen.add(key)
                    threats.append(Threat(
                        priority="P3",
                        category="CALLSIGN",
                        title="Callsign with appended letter",
                        source_section="ATC Flight Plan",
                        highlight_text=line,
                        why_it_matters="Callsign com letra appended aumenta a necessidade de disciplina nas comunicações.",
                        expected_crew_action="Reforçar atenção a listening e readback discipline.",
                        affected_phase="General",
                        affected_area="General",
                        page_number=pnum,
                    ))

        # Weather / alternates / thunderstorms / gusts / windshear / CB / GNSS
        weather_patterns = [
            (r"\bgnss\b.*\bsev\b|\bswx\b.*\bgnss\b", "GNSS"),
            (r"\bwindshear\b", "WINDSHEAR"),
            (r"\btsra\b|\bvcts\b|\bcb\b|\bthunderstorm\b|\bembd ts\b", "TS"),
            (r"g\d{2,3}kt|gust", "GUST"),
            (r"\btempo\b|\bprob30\b|\bprob40\b", "TEMPO"),
            (r"rff|rescue and fire|fire fighting", "RFF"),
            (r"raim outage|rnp 0\.1|gnss interference", "NAV"),
        ]
        for line, tag in _find_matches(lines, weather_patterns):
            key = (line, pnum)
            if key in seen:
                continue
            seen.add(key)
            if tag == "GNSS":
                threats.append(Threat("P2", "NAV", "GNSS/space weather degradation", "Weather / Advisory", line,
                                      "O briefing indica degradação potencial de GNSS, relevante para navegação e monitorização.",
                                      "Reforçar cross-checking de navegação e awareness para contingências GNSS.",
                                      "Enroute", "General", pnum))
            elif tag == "WINDSHEAR":
                threats.append(Threat("P2", "MET", "Possible windshear", "Weather List", line,
                                      "Windshear é ameaça relevante em fase crítica de voo.",
                                      "Briefar cues, escape guidance e estratégia de monitorização.",
                                      "Departure", "Departure/Arrival", pnum))
            elif tag == "TS":
                threats.append(Threat("P2", "MET", "Convective activity / thunderstorms", "Weather List / SIGMET", line,
                                      "Atividade convectiva aumenta workload, desvios táticos e risco de turbulência/precipitação forte.",
                                      "Briefar weather avoidance e monitorização radar/ATC.",
                                      "Departure", "General", pnum))
            elif tag == "GUST":
                threats.append(Threat("P2", "MET", "Strong gusty wind", "Weather List", line,
                                      "Rajadas fortes podem afetar a fase de aproximação/aterragem ou descolagem.",
                                      "Confirmar runway expectation e estratégia para vento rajado.",
                                      "Arrival", "Destination/Alternate", pnum))
            elif tag == "TEMPO":
                threats.append(Threat("P3", "MET", "Variable weather / TEMPO-PROB conditions", "Weather List", line,
                                      "Condições variáveis podem aumentar complexidade operacional e exigem awareness.",
                                      "Verificar aplicabilidade temporal e considerar no briefing se coincidir com a janela relevante.",
                                      "General", "General", pnum))
            elif tag == "RFF":
                threats.append(Threat("P2", "AERODROME", "RFF downgraded", "NOTAM / Dispatch", line,
                                      "Downgrade de RFF num aeródromo relevante para desvio deve entrar no briefing.",
                                      "Confirmar adequacy do aeródromo para eventual desvio.",
                                      "Diversion", "Alternate/Enroute alternate", pnum))
            elif tag == "NAV":
                threats.append(Threat("P2", "NAV", "Navigation capability limitation", "RAIM / NOTAM / Advisory", line,
                                      "Uma limitação de navegação pode afetar procedimentos ou a lógica de desvio.",
                                      "Rever impacto nos procedimentos e alternantes relevantes.",
                                      "Enroute", "General", pnum))

        # ETOPS / ETP / Enroute alternate awareness
        if any(tok in full_lower for tok in ["etops summary", "etp1", "entry1", "exit1", "ralt/"]):
            etops_lines = [ln for ln in lines if any(tok in ln.lower() for tok in ["entry1", "etp1", "exit1", "ralt/", "enrte altns"])]
            for line in etops_lines:
                key = (line, pnum)
                if key in seen:
                    continue
                seen.add(key)
                threats.append(Threat(
                    priority="P3",
                    category="ALT_ETOPS",
                    title="ETOPS / en-route alternate awareness",
                    source_section="ETOPS Summary / ATC Flight Plan",
                    highlight_text=line,
                    why_it_matters="A estrutura de entry/ETP/exit e alternantes en-route deve entrar no briefing como awareness.",
                    expected_crew_action="Brief curto sobre alternantes en-route, ETP e lógica de desvio.",
                    affected_phase="Enroute",
                    affected_area="Enroute",
                    page_number=pnum,
                ))

        # Procedure cancellations/closures
        closure_patterns = [(r"closed|closure|canceled|cancelled|u/s|unserviceable", "CLOSE")]
        for line, _ in _find_matches(lines, closure_patterns):
            if any(x in line.lower() for x in ["runway", "rwy", "taxiway", "vor", "ils", "procedure"]):
                key = (line, pnum)
                if key in seen:
                    continue
                seen.add(key)
                threats.append(Threat(
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
                ))

        # Tropopause proximity heuristic
        if re.search(r"\b(39|40)\b", text) and ("trop" in full_lower or "tropopause" in full_lower or re.search(r"\bfl390\b|\b390\b", full_lower)):
            line = "Tropopause/FL proximity requires CAT awareness"
            key = (line, pnum)
            if key not in seen:
                seen.add(key)
                threats.append(Threat(
                    priority="P2",
                    category="MET",
                    title="Tropopause proximity / CAT awareness",
                    source_section="Operational Flight Plan",
                    highlight_text=line,
                    why_it_matters="Nível de voo próximo da tropopause pode aumentar o risco de clear air turbulence.",
                    expected_crew_action="Antecipar possível CAT e gerir awareness de cabine e seat belts.",
                    affected_phase="Enroute",
                    affected_area="Cruise",
                    page_number=pnum,
                ))

    # Sort by priority then page
    order = {"P1": 0, "P2": 1, "P3": 2}
    threats.sort(key=lambda t: (order[t.priority], t.page_number, t.title))
    return threats
