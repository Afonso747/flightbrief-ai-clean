from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Iterable

from .models import Threat
from .airport_coords import AIRPORT_COORDS
from .runway_db import RUNWAY_DB


NEGATIVE_PATTERNS = [
    r"\bNO RAIM OUTAGES\b",
    r"\bNO OUTAGES\b",
    r"\bNIL\b",
    r"\bNO WX DATA AVAILABLE\b",
]

RELEVANT_AIRPORTS = set(AIRPORT_COORDS.keys())

ALTERNATE_LIKE_AIRPORTS = {
    "TXKF", "KBGR", "CYHZ", "CYJT", "CYYT", "CYQX", "CYUL", "CYOW", "CYYR",
    "LPPD", "LPLA", "LPAZ", "LPFR", "LPMA", "LPPS", "LEMD", "LEZL", "LEMG",
    "LEVC", "LEBL", "LEPA", "GVAC", "GOBD", "DGAA", "DXXX", "DIAP", "FNLU",
    "FNBJ", "DAAG", "DAAT", "LFBO", "LFPO", "LFPG", "LFBD", "LFRS", "LIRF",
    "LIRA", "LIRN", "LFQQ", "EBBR", "ELLX", "EHAM", "EDDF", "EDDM", "EDDH",
    "EDDB", "LIMC", "LSZH", "LSGG", "LOWW", "LKPR", "EPWA", "LHBP", "LGAV",
    "LLBG", "LCLK", "EKCH", "ESSA", "ENGM", "EGLL", "EGKK", "EINN", "EIDW",
    "KRDU", "KPHL", "KEWR", "KJFK", "KMIA", "KBOS", "KFLL", "KPSM",
    "KMKE", "KORD", "KDEN", "KSLC", "KOAK", "KSAN", "KLAS", "KSFO", "KLAX",
}


def _lines(text: str) -> Iterable[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _is_negative_line(line: str) -> bool:
    return any(re.search(p, line, re.IGNORECASE) for p in NEGATIVE_PATTERNS)


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


def _minutes_to_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh:02d}:{mm:02d}Z"


def _extract_brief_date_day(pages: list[dict]) -> int | None:
    joined = "\n".join(page["text"] for page in pages[:5])

    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", joined)
    if m:
        return int(m.group(3))

    m = re.search(r"\b(\d{2})[A-Z]{3}\d{4}\b", joined)
    if m:
        return int(m.group(1))

    return None


def _extract_route_context(pages: list[dict]) -> dict:
    joined = "\n".join(page["text"] for page in pages[:12])

    etd = None
    eta = None
    departure = None
    destination = None
    etops_windows: dict[str, tuple[int, int]] = {}

    etd_match = re.search(r"\bETD\s+(\d{4})\b", joined)
    eta_match = re.search(r"\bETA\s+(\d{4})\b", joined)

    if etd_match:
        etd = _hhmm_to_minutes(etd_match.group(1))
    if eta_match:
        eta = _hhmm_to_minutes(eta_match.group(1))

    cover_match = re.search(
        r"\b[A-Z]{3}\s+(\d{2}:\d{2}).*?\b[A-Z]{3}\s+(\d{2}:\d{2})",
        joined,
        re.DOTALL,
    )
    if cover_match and (etd is None or eta is None):
        etd = _hhmm_to_minutes(cover_match.group(1).replace(":", ""))
        eta = _hhmm_to_minutes(cover_match.group(2).replace(":", ""))

    route_match = re.search(r"\b[A-Z]{3,}\d+\s+\d{2}[A-Z]{3}\d{4}\s+([A-Z]{4})\s+([A-Z]{4})\b", joined)
    if route_match:
        departure = route_match.group(1)
        destination = route_match.group(2)

    if etd is not None and eta is not None and eta < etd:
        eta += 24 * 60

    for ap, start_hh, start_mm, end_hh, end_mm in re.findall(
        r"\b([A-Z]{4})\s+(\d{2}):(\d{2})\s+(\d{2}):(\d{2})\b",
        joined,
    ):
        start = int(start_hh) * 60 + int(start_mm)
        end = int(end_hh) * 60 + int(end_mm)

        if etd is not None and end < start:
            end += 24 * 60
        if etd is not None and start < etd - 12 * 60:
            start += 24 * 60
            end += 24 * 60

        etops_windows[ap] = (start, end)

    return {
        "etd": etd,
        "eta": eta,
        "departure": departure,
        "destination": destination,
        "etops_windows": etops_windows,
        "brief_day": _extract_brief_date_day(pages),
    }


def _parse_latlon_compact(value: str) -> float:
    hemi = value[0]
    body = value[1:]

    if hemi in {"N", "S"}:
        deg = int(body[:2])
        minutes = float(body[2:])
    else:
        deg = int(body[:3])
        minutes = float(body[3:])

    decimal = deg + minutes / 60.0
    if hemi in {"S", "W"}:
        decimal *= -1
    return decimal


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    km = r_km * c
    return km * 0.539957


def _to_cartesian(lat: float, lon: float) -> tuple[float, float, float]:
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    x = math.cos(lat_r) * math.cos(lon_r)
    y = math.cos(lat_r) * math.sin(lon_r)
    z = math.sin(lat_r)
    return (x, y, z)


def _nearest_time_on_segment(ap_lat: float, ap_lon: float, p1: dict, p2: dict) -> tuple[float, float]:
    a = _to_cartesian(p1["lat"], p1["lon"])
    b = _to_cartesian(p2["lat"], p2["lon"])
    p = _to_cartesian(ap_lat, ap_lon)

    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])

    ab2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
    if ab2 == 0:
        return _haversine_nm(ap_lat, ap_lon, p1["lat"], p1["lon"]), p1["time"]

    t = (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / ab2
    t = max(0.0, min(1.0, t))

    x = a[0] + t * ab[0]
    y = a[1] + t * ab[1]
    z = a[2] + t * ab[2]

    norm = math.sqrt(x * x + y * y + z * z)
    if norm == 0:
        return _haversine_nm(ap_lat, ap_lon, p1["lat"], p1["lon"]), p1["time"]

    x /= norm
    y /= norm
    z /= norm

    lat = math.degrees(math.asin(z))
    lon = math.degrees(math.atan2(y, x))

    dist = _haversine_nm(ap_lat, ap_lon, lat, lon)
    time_interp = p1["time"] + t * (p2["time"] - p1["time"])
    return dist, time_interp


def _parse_route_times(pages: list[dict]) -> dict[str, int]:
    point_times: dict[str, int] = {}

    for page in pages:
        lines = _lines(page["text"])
        for line in lines:
            m = re.match(r"^([A-Z0-9-]+)\s*\|.*\|(\d{4})\|", line)
            if m:
                point = m.group(1).strip()
                tot = m.group(2)
                point_times[point] = _hhmm_to_minutes(tot)

    return point_times


def _parse_route_coords(pages: list[dict]) -> dict[str, tuple[float, float]]:
    route_coords: dict[str, tuple[float, float]] = {}

    for page in pages:
        lines = _lines(page["text"])
        i = 0
        while i < len(lines) - 1:
            line1 = lines[i]
            line2 = lines[i + 1]

            m1 = re.match(r"^([A-Z0-9-]+)\s*\|\s*([NS]\d{4,5}\.\d)\s*\|", line1)
            m2 = re.match(r"^\|\s*([EW]\d{5,6}\.\d)\s*\|", line2)

            if m1 and m2:
                point = m1.group(1).strip()
                lat = _parse_latlon_compact(m1.group(2))
                lon = _parse_latlon_compact(m2.group(1))
                route_coords[point] = (lat, lon)
                i += 2
                continue

            i += 1

    return route_coords


def _build_route_points_with_time_and_coords(pages: list[dict], etd: int | None) -> list[dict]:
    point_times = _parse_route_times(pages)
    point_coords = _parse_route_coords(pages)

    route_points = []
    for point, (lat, lon) in point_coords.items():
        if point not in point_times:
            continue

        abs_time = point_times[point]
        if etd is not None and abs_time < etd - 12 * 60:
            abs_time += 24 * 60

        route_points.append({"point": point, "lat": lat, "lon": lon, "time": abs_time})

    route_points.sort(key=lambda x: x["time"])
    return route_points


def _time_overlap_minutes(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def _align_window_to_reference(start: int, end: int, ref_start: int) -> tuple[int, int]:
    if end < start:
        end += 24 * 60
    if start < ref_start - 12 * 60:
        start += 24 * 60
        end += 24 * 60
    return start, end


def _parse_taf_group_window(line: str, brief_day: int | None) -> tuple[int | None, int | None]:
    if brief_day is None:
        return None, None

    def ddhh_to_abs_minutes(ddhh: str) -> int:
        day = int(ddhh[:2])
        hour = int(ddhh[2:])
        day_offset = day - brief_day
        if day_offset < 0:
            day_offset += 31
        return day_offset * 24 * 60 + hour * 60

    m = re.search(r"\bPROB\d{2}\s+TEMPO\s+(\d{4})/(\d{4})\b", line)
    if m:
        return ddhh_to_abs_minutes(m.group(1)), ddhh_to_abs_minutes(m.group(2))

    m = re.search(r"\bTEMPO\s+(\d{4})/(\d{4})\b", line)
    if m:
        return ddhh_to_abs_minutes(m.group(1)), ddhh_to_abs_minutes(m.group(2))

    m = re.search(r"\bBECMG\s+(\d{4})/(\d{4})\b", line)
    if m:
        return ddhh_to_abs_minutes(m.group(1)), ddhh_to_abs_minutes(m.group(2))

    m = re.search(r"\bFM(\d{6})\b", line)
    if m:
        ddhh = m.group(1)[:4]
        start = ddhh_to_abs_minutes(ddhh)
        return start, start + 360

    m = re.search(r"\bFT\s+\d{6}\s+(\d{4})/(\d{4})\b", line)
    if m:
        return ddhh_to_abs_minutes(m.group(1)), ddhh_to_abs_minutes(m.group(2))

    return None, None


def _detect_weather_line_type(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("SA "):
        return "METAR"
    if stripped.startswith("FT "):
        return "TAF_BASE"
    if stripped.startswith("TEMPO "):
        return "TAF_GROUP"
    if re.match(r"^PROB\d{2}\s+TEMPO ", stripped):
        return "TAF_GROUP"
    if stripped.startswith("BECMG "):
        return "TAF_GROUP"
    if re.match(r"^FM\d{6}", stripped):
        return "TAF_GROUP"
    return "OTHER"


def _line_has_weather_threat(line: str) -> bool:
    lower = line.lower()
    return bool(
        re.search(
            r"\btsra\b|\bvcts\b|\bcb\b|\btcu\b|\b\+ra\b|\b-ra\b|\bra\b|\bfg\b|\bdz\b|\bsn\b|\bfzra\b|\bdu\b|\bmifg\b|\bbkn0\d{2}\b|\bovc0\d{2}\b|\b\d+\s*\d/\dsm\b|\b\d+sm\b|\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt|ws020|windshear|\b\d{4}\b",
            lower,
        )
    )


def _extract_visibility(line: str, wx_type: str) -> tuple[float | None, str | None]:
    lower = line.lower()

    if wx_type == "METAR":
        m = re.search(r"\b(\d+)\s+(\d)/(\d)sm\b", lower)
        if m:
            whole = int(m.group(1))
            num = int(m.group(2))
            den = int(m.group(3))
            return whole + num / den, "sm"

        m = re.search(r"\b(\d)/(\d)sm\b", lower)
        if m:
            return int(m.group(1)) / int(m.group(2)), "sm"

        m = re.search(r"\b(\d+(?:\.\d+)?)sm\b", lower)
        if m:
            return float(m.group(1)), "sm"

        return None, None

    patterns = [
        r"PROB\d{2}\s+TEMPO\s+\d{4}/\d{4}\s+(?:\d{3}V\d{3}\s+)?(?:\d{5}KT|\d{3}\d{2,3}(?:G\d{2,3})?KT|VRB\d{2,3}(?:G\d{2,3})?KT)\s+(\d{4})\b",
        r"TEMPO\s+\d{4}/\d{4}\s+(?:\d{3}V\d{3}\s+)?(?:\d{5}KT|\d{3}\d{2,3}(?:G\d{2,3})?KT|VRB\d{2,3}(?:G\d{2,3})?KT)\s+(\d{4})\b",
        r"BECMG\s+\d{4}/\d{4}\s+(?:\d{3}V\d{3}\s+)?(?:\d{5}KT|\d{3}\d{2,3}(?:G\d{2,3})?KT|VRB\d{2,3}(?:G\d{2,3})?KT)\s+(\d{4})\b",
        r"FM\d{6}\s+(?:\d{3}V\d{3}\s+)?(?:\d{5}KT|\d{3}\d{2,3}(?:G\d{2,3})?KT|VRB\d{2,3}(?:G\d{2,3})?KT)\s+(\d{4})\b",
        r"FT\s+\d{6}\s+\d{4}/\d{4}\s+(?:\d{3}V\d{3}\s+)?(?:\d{5}KT|\d{3}\d{2,3}(?:G\d{2,3})?KT|VRB\d{2,3}(?:G\d{2,3})?KT)\s+(\d{4})\b",
    ]

    for pat in patterns:
        m = re.search(pat, line)
        if m:
            return float(int(m.group(1))), "m"

    return None, None


def _extract_ceiling_hundreds_ft(line: str) -> int | None:
    bkn = re.findall(r"\bBKN(\d{3})\b", line)
    ovc = re.findall(r"\bOVC(\d{3})\b", line)
    vals = [int(x) for x in bkn + ovc]
    if not vals:
        return None
    return min(vals)


def _extract_wind(line: str) -> tuple[int | None, int | None, int | None]:
    m = re.search(r"\b(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b", line)
    if not m:
        return None, None, None

    direction_txt = m.group(1)
    speed = int(m.group(2))
    gust = int(m.group(3)) if m.group(3) else None

    if direction_txt == "VRB":
        return None, speed, gust

    return int(direction_txt), speed, gust


def _min_angle_between_deg(a: int, b: int) -> int:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def _wind_angle_to_primary_runway(airport: str, wind_dir: int | None) -> int | None:
    if wind_dir is None or airport not in RUNWAY_DB:
        return None
    headings = RUNWAY_DB[airport]["headings"]
    return min(_min_angle_between_deg(wind_dir, h) for h in headings)


def _get_airport_reference_time(airport: str, ctx: dict) -> int | None:
    etd = ctx["etd"]
    eta = ctx["eta"]
    departure = ctx["departure"]
    destination = ctx["destination"]
    etops_windows = ctx["etops_windows"]
    route_points = ctx["route_points"]

    if etd is None or eta is None:
        return None

    if airport == departure:
        return etd

    if airport == destination:
        return eta

    if airport in etops_windows:
        start, end = etops_windows[airport]
        return int((start + end) / 2)

    if airport in AIRPORT_COORDS and len(route_points) >= 2:
        ap_lat, ap_lon = AIRPORT_COORDS[airport]
        best_dist = float("inf")
        best_time = None

        for i in range(len(route_points) - 1):
            p1 = route_points[i]
            p2 = route_points[i + 1]
            dist, t = _nearest_time_on_segment(ap_lat, ap_lon, p1, p2)
            if dist < best_dist:
                best_dist = dist
                best_time = int(round(t))

        if best_time is not None:
            return best_time

    if airport in ALTERNATE_LIKE_AIRPORTS:
        return eta

    return None


def _get_airport_applicability_window(airport: str, ctx: dict) -> tuple[int | None, int | None]:
    ref_time = _get_airport_reference_time(airport, ctx)
    if ref_time is None:
        return None, None

    departure = ctx["departure"]
    destination = ctx["destination"]

    if airport == departure:
        return max(0, ref_time - 60), ref_time + 60

    if airport == destination:
        return max(0, ref_time - 60), ref_time + 120

    return max(0, ref_time - 60), ref_time + 60


def _is_marginal_weather(line: str, airport: str, wx_type: str) -> tuple[bool, list[str]]:
    reasons = []

    ceiling = _extract_ceiling_hundreds_ft(line)
    if ceiling is not None and ceiling <= 6:
        reasons.append("low ceiling")

    vis, unit = _extract_visibility(line, wx_type)
    if vis is not None:
        if unit == "sm" and vis <= 1.5:
            reasons.append("low visibility")
        elif unit == "m" and vis <= 2000:
            reasons.append("low visibility")

    wind_dir, speed, gust = _extract_wind(line)
    angle = _wind_angle_to_primary_runway(airport, wind_dir)

    if speed is not None and speed > 15 and angle is not None and angle >= 30:
        reasons.append("strong off-axis wind")

    if gust is not None and gust > 17 and angle is not None and angle >= 30:
        reasons.append("strong off-axis gust")

    lower = line.lower()
    phenomena_patterns = [
        r"\bfg\b", r"\bdz\b", r"\bsn\b", r"\bfzra\b", r"\bdu\b", r"\bmifg\b",
        r"\bcb\b", r"\btcu\b", r"\bts\b", r"\btsra\b", r"\bra\b"
    ]
    if any(re.search(p, lower) for p in phenomena_patterns):
        reasons.append("relevant phenomena")

    return (len(reasons) > 0), reasons


def _classify_weather_line(line: str, airport: str, window_label: str, wx_type: str) -> tuple[str, str, str, str, str]:
    lower = line.lower()

    is_marginal, marginal_reasons = _is_marginal_weather(line, airport, wx_type)
    if is_marginal:
        return (
            "P2",
            "ALT_ETOPS",
            "Marginal weather",
            f"Condição meteorológica marginal em {airport} dentro da janela operacional aplicável ({window_label}) devido a: {', '.join(marginal_reasons)}.",
            "Rever adequacy, minima e utilidade real do aeroporto para desvio/alternante.",
        )

    if "ws020" in lower or "windshear" in lower:
        return (
            "P2",
            "MET",
            "Windshear / low-level windshear",
            f"Windshear em {airport} dentro da janela operacional aplicável ({window_label}) aumenta workload e deve entrar no briefing.",
            "Reforçar briefing de departure/arrival e awareness para windshear recovery.",
        )

    if re.search(r"\btsra\b|\bvcts\b|\bcb\b|\btcu\b|\b\+ra\b|\b-ra\b|\bra\b", lower):
        return (
            "P2",
            "MET",
            "Convective activity / precipitation",
            f"Fenómenos convectivos ou precipitação em {airport} dentro da janela operacional aplicável ({window_label}) aumentam workload e podem exigir mitigação.",
            "Briefar weather avoidance e monitorização.",
        )

    if re.search(r"\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt", lower):
        return (
            "P2",
            "MET",
            "Strong gusty wind",
            f"Rajadas fortes previstas em {airport} dentro da janela operacional aplicável ({window_label}) podem afetar a operação.",
            "Confirmar runway expectation e estratégia para vento rajado.",
        )

    return (
        "P3",
        "MET",
        "Weather awareness",
        f"Condição meteorológica relevante em {airport} dentro da janela operacional aplicável ({window_label}).",
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


def _extract_weather_threats_from_airport_block(airport: str, lines: list[str], page_number: int, ctx: dict) -> list[Threat]:
    threats: list[Threat] = []

    if airport not in RELEVANT_AIRPORTS and airport not in {ctx.get("departure"), ctx.get("destination")} and airport not in ctx.get("etops_windows", {}):
        return threats

    app_start, app_end = _get_airport_applicability_window(airport, ctx)
    if app_start is None or app_end is None:
        return threats

    window_label = f"{_minutes_to_hhmm(app_start)}–{_minutes_to_hhmm(app_end)}"

    for line in lines:
        if _is_negative_line(line):
            continue

        wx_type = _detect_weather_line_type(line)
        if wx_type == "OTHER":
            continue
        if not _line_has_weather_threat(line):
            continue

        start, end = _parse_taf_group_window(line, ctx.get("brief_day"))

        if wx_type == "METAR":
            start, end = app_start, app_end
        elif wx_type in {"TAF_GROUP", "TAF_BASE"}:
            if start is None or end is None:
                continue
        else:
            continue

        start, end = _align_window_to_reference(start, end, app_start)

        if not _time_overlap_minutes(start, end, app_start, app_end):
            continue

        priority, category, title, why, expected_action = _classify_weather_line(line, airport, window_label, wx_type)

        affected_phase = "General"
        if airport == ctx.get("departure"):
            affected_phase = "Departure"
        elif airport == ctx.get("destination"):
            affected_phase = "Arrival"
        elif airport in ALTERNATE_LIKE_AIRPORTS or airport in ctx.get("etops_windows", {}):
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
    ctx = _extract_route_context(pages)
    ctx["route_points"] = _build_route_points_with_time_and_coords(pages, ctx["etd"])

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
                raw_threats.extend(_extract_weather_threats_from_airport_block(airport, airport_lines, pnum, ctx))

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
            airports_in_line = re.findall(r"\b[A-Z]{4}\b", line)
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
