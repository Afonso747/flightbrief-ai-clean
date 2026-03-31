from __future__ import annotations

import math
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

# Lista fechada da companhia (normalizada e sem duplicados)
RELEVANT_AIRPORTS = {
    "KLAX", "KSFO", "KLAS", "KSAN", "KOAK", "KSLC", "KDEN", "KORD", "KMKE",
    "KDTW", "KRDU", "KIAD", "KPHL", "KEWR", "KJFK", "KMIA", "KBOS", "KFLL",
    "TXKF", "KPSM", "KBGR", "CYHZ", "CYJT", "CYYT", "CYQX", "CYUL", "CYOW",
    "CYYR", "MMUN", "SVMC", "SVMU", "SOCA", "SBBE", "SGSL", "SBFZ", "SBSG",
    "SBRF", "SBSV", "SBBR", "SBCF", "SBGL", "SBGR", "SBCT", "SBFL", "SBPA",
    "GVAC", "GOBD", "DGAA", "DXXX", "DIAP", "FKKD", "FOOL", "FNLU", "FNBJ",
    "FQMA", "DNKN", "GQNO", "GMML", "GCTS", "GCXO", "GCLP", "GMAD", "GMMN",
    "LPFR", "LPMA", "LPPS", "LPPT", "LEMD", "LEZL", "LEMG", "LEVC", "LEBL",
    "DAAG", "DAAT", "LEPA", "LFBO", "LFPO", "LFPG", "LFBD", "LFRS", "LIRF",
    "LIRA", "LIRN", "LFQQ", "EBBR", "ELLX", "EHAM", "EDDF", "EDDM", "EDDH",
    "EDDB", "LIMC", "LSZH", "LSGG", "LOWW", "LKPR", "EPWA", "LHBP", "LGAV",
    "LLBG", "LCLK", "EKCH", "ESSA", "ENGM", "EGLL", "EGKK", "EINN", "EIDW",
    "LPPD", "LPLA", "LPAZ",
}

# Subconjunto tratado como alternates / diversion-like por defeito
ALTERNATE_LIKE_AIRPORTS = {
    "TXKF", "KBGR", "CYHZ", "CYJT", "CYYT", "CYQX", "CYUL", "CYOW", "CYYR",
    "LPPD", "LPLA", "LPAZ", "LPFR", "LPMA", "LPPS", "LEMD", "LEZL", "LEMG",
    "LEVC", "LEBL", "LEPA", "GVAC", "GOBD", "DGAA", "DXXX", "DIAP", "FKKD",
    "FOOL", "FNLU", "FNBJ", "FQMA", "DNKN", "GQNO", "GMML", "GCTS", "GCXO",
    "GCLP", "GMAD", "GMMN", "DAAG", "DAAT", "LFBO", "LFPO", "LFPG", "LFBD",
    "LFRS", "LIRF", "LIRA", "LIRN", "LFQQ", "EBBR", "ELLX", "EHAM", "EDDF",
    "EDDM", "EDDH", "EDDB", "LIMC", "LSZH", "LSGG", "LOWW", "LKPR", "EPWA",
    "LHBP", "LGAV", "LLBG", "LCLK", "EKCH", "ESSA", "ENGM", "EGLL", "EGKK",
    "EINN", "EIDW", "KRDU", "KPHL", "KEWR", "KJFK", "KMIA", "KBOS", "KFLL",
    "KPSM", "KMKE", "KDTW", "KORD", "KDEN", "KSLC", "KOAK", "KSAN", "KLAS",
    "KSFO", "KLAX", "MMUN", "SVMC", "SVMU", "SOCA", "SBBE", "SGSL", "SBFZ",
    "SBSG", "SBRF", "SBSV", "SBBR", "SBCF", "SBGL", "SBGR", "SBCT", "SBFL",
    "SBPA",
}

# Coordenadas dos aeroportos mais relevantes para esta fase do protótipo.
# Se um aeroporto não estiver aqui, o motor ignora a triangulação desse aeroporto
# e cai para as regras de departure/destination/ETOPS quando aplicável.
AIRPORT_COORDS = {
    "KLAX": (33.9425, -118.4081),
    "KSFO": (37.6188, -122.3754),
    "KLAS": (36.0801, -115.1522),
    "KSAN": (32.7338, -117.1933),
    "KOAK": (37.7213, -122.2210),
    "KSLC": (40.7899, -111.9791),
    "KDEN": (39.8561, -104.6737),
    "KORD": (41.9742, -87.9073),
    "KMKE": (42.9472, -87.8966),
    "KDTW": (42.2124, -83.3534),
    "KRDU": (35.8776, -78.7875),
    "KIAD": (38.9445, -77.4558),
    "KPHL": (39.8744, -75.2424),
    "KEWR": (40.6895, -74.1745),
    "KJFK": (40.6413, -73.7781),
    "KMIA": (25.7959, -80.2870),
    "KBOS": (42.3656, -71.0096),
    "KFLL": (26.0726, -80.1527),
    "TXKF": (32.3639, -64.6787),
    "KPSM": (43.0781, -70.8233),
    "KBGR": (44.8074, -68.8281),
    "CYHZ": (44.8808, -63.5086),
    "CYJT": (48.5442, -58.5499),
    "CYYT": (47.6186, -52.7519),
    "CYQX": (48.9369, -54.5681),
    "CYUL": (45.4706, -73.7408),
    "CYOW": (45.3225, -75.6692),
    "CYYR": (53.3192, -60.4258),
    "MMUN": (21.0365, -86.8771),
    "SVMC": (10.5582, -63.9816),
    "SVMU": (10.9126, -63.9666),
    "SOCA": (4.8198, -52.3604),
    "SBBE": (-1.3793, -48.4763),
    "SGSL": (-2.5854, -44.2341),
    "SBFZ": (-3.7763, -38.5326),
    "SBSG": (-5.7681, -35.3761),
    "SBRF": (-8.1265, -34.9236),
    "SBSV": (-12.9086, -38.3225),
    "SBBR": (-15.8692, -47.9208),
    "SBCF": (-19.6244, -43.9719),
    "SBGL": (-22.8090, -43.2506),
    "SBGR": (-23.4356, -46.4731),
    "SBCT": (-25.5285, -49.1758),
    "SBFL": (-27.6703, -48.5525),
    "SBPA": (-29.9944, -51.1714),
    "GVAC": (14.9245, -23.4935),
    "GOBD": (14.6708, -17.0733),
    "DGAA": (5.6052, -0.1668),
    "DXXX": (6.1656, 1.2545),
    "DIAP": (5.2614, -3.9263),
    "FKKD": (4.0061, 9.7195),
    "FOOL": (0.4586, 9.4123),
    "FNLU": (-8.8584, 13.2312),
    "FNBJ": (-12.6090, 13.4037),
    "FQMA": (-25.9208, 32.5726),
    "DNKN": (12.0476, 8.5246),
    "GQNO": (18.0982, -15.9479),
    "GMML": (33.3675, -7.5899),
    "GCTS": (28.0445, -16.5725),
    "GCXO": (28.4827, -16.3415),
    "GCLP": (27.9319, -15.3866),
    "GMAD": (30.3250, -9.4131),
    "GMMN": (33.5613, -7.6608),
    "LPFR": (37.0144, -7.9659),
    "LPMA": (32.6979, -16.7745),
    "LPPS": (33.0734, -16.3500),
    "LPPT": (38.7742, -9.1342),
    "LPPD": (37.7412, -25.6979),
    "LPLA": (38.7618, -27.0908),
    "LPAZ": (36.9714, -25.1706),
    "LEMD": (40.4722, -3.5608),
    "LEZL": (37.4180, -5.8931),
    "LEMG": (36.6749, -4.4991),
    "LEVC": (39.4893, -0.4816),
    "LEBL": (41.2971, 2.0785),
    "DAAG": (36.6910, 3.2154),
    "DAAT": (22.8115, 5.4511),
    "LEPA": (39.5517, 2.7388),
    "LFBO": (43.6293, 1.3630),
    "LFPO": (48.7262, 2.3652),
    "LFPG": (49.0097, 2.5479),
    "LFBD": (44.8283, -0.7156),
    "LFRS": (47.1532, -1.6107),
    "LIRF": (41.8003, 12.2389),
    "LIRA": (41.6545, 12.4452),
    "LIRN": (40.8860, 14.2908),
    "LFQQ": (50.5633, 3.0872),
    "EBBR": (50.9010, 4.4844),
    "ELLX": (49.6233, 6.2044),
    "EHAM": (52.3105, 4.7683),
    "EDDF": (50.0379, 8.5622),
    "EDDM": (48.3538, 11.7861),
    "EDDH": (53.6304, 9.9882),
    "EDDB": (52.3667, 13.5033),
    "LIMC": (45.6301, 8.7231),
    "LSZH": (47.4582, 8.5555),
    "LSGG": (46.2381, 6.1089),
    "LOWW": (48.1103, 16.5697),
    "LKPR": (50.1008, 14.2600),
    "EPWA": (52.1657, 20.9671),
    "LHBP": (47.4369, 19.2556),
    "LGAV": (37.9364, 23.9475),
    "LLBG": (32.0114, 34.8867),
    "LCLK": (34.8751, 33.6249),
    "EKCH": (55.6181, 12.6561),
    "ESSA": (59.6519, 17.9186),
    "ENGM": (60.1939, 11.1004),
    "EGLL": (51.4700, -0.4543),
    "EGKK": (51.1537, -0.1821),
    "EINN": (52.7020, -8.9248),
    "EIDW": (53.4213, -6.2701),
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


def _minutes_to_hhmm(minutes: int) -> str:
    minutes = minutes % (24 * 60)
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh:02d}:{mm:02d}Z"


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

    # WEATHER SUITABILITY PERIOD / ETOPS windows
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


def _nearest_time_on_segment(
    ap_lat: float,
    ap_lon: float,
    p1: dict,
    p2: dict,
) -> tuple[float, float]:
    """
    Approximate nearest point on segment using 3D cartesian interpolation.
    Returns:
      (distance_nm, interpolated_time_minutes)
    """
    a = _to_cartesian(p1["lat"], p1["lon"])
    b = _to_cartesian(p2["lat"], p2["lon"])
    p = _to_cartesian(ap_lat, ap_lon)

    ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    ap = (p[0] - a[0], p[1] - a[1], p[2] - a[2])

    ab2 = ab[0] ** 2 + ab[1] ** 2 + ab[2] ** 2
    if ab2 == 0:
        dist = _haversine_nm(ap_lat, ap_lon, p1["lat"], p1["lon"])
        return dist, p1["time"]

    t = (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / ab2
    t = max(0.0, min(1.0, t))

    x = a[0] + t * ab[0]
    y = a[1] + t * ab[1]
    z = a[2] + t * ab[2]

    norm = math.sqrt(x * x + y * y + z * z)
    if norm == 0:
        dist = _haversine_nm(ap_lat, ap_lon, p1["lat"], p1["lon"])
        return dist, p1["time"]

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
            m = re.match(r"^([A-Z0-9-]+)\s*\|.*\|(\d{4})\|(?:\s*\|\s*)*$", line)
            if m:
                point = m.group(1).strip()
                tot = m.group(2)
                point_times[point] = _hhmm_to_minutes(tot)
                continue

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

        route_points.append(
            {
                "point": point,
                "lat": lat,
                "lon": lon,
                "time": abs_time,
            }
        )

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


def _classify_weather_line(line: str, airport: str, window_label: str) -> tuple[str, str, str, str, str]:
    lower = line.lower()

    if "ws020" in lower or "windshear" in lower:
        return (
            "P2",
            "MET",
            "Windshear / low-level windshear",
            f"Windshear em {airport} dentro da janela operacional aplicável ({window_label}) aumenta workload e deve entrar no briefing.",
            "Reforçar briefing de departure/arrival e awareness para windshear recovery.",
        )

    if re.search(r"\btsra\b|\bvcts\b|\bcb\b|\btcu\b|\b\+ra\b", lower):
        return (
            "P2",
            "MET",
            "Convective activity / thunderstorms",
            f"Atividade convectiva prevista em {airport} dentro da janela operacional aplicável ({window_label}) aumenta workload, desvios táticos e risco de turbulência/precipitação forte.",
            "Briefar weather avoidance e monitorização radar/ATC.",
        )

    if re.search(r"\b\d{2,3}g\d{2,3}kt\b|g\d{2,3}kt", lower):
        return (
            "P2",
            "MET",
            "Strong gusty wind",
            f"Rajadas fortes previstas em {airport} dentro da janela operacional aplicável ({window_label}) podem afetar a fase de aproximação/aterragem ou descolagem.",
            "Confirmar runway expectation e estratégia para vento rajado.",
        )

    if airport in ALTERNATE_LIKE_AIRPORTS and re.search(r"\bbr\b|\bovc0\d{2}\b|\bbkn0\d{2}\b|\b-fzdz\b|\bshsn\b|\bshra\b|\b-ra\b|\bsn\b", lower):
        return (
            "P2",
            "ALT_ETOPS",
            "Marginal alternate / diversion weather",
            f"Meteorologia marginal em {airport}, relevante dentro da janela operacional aplicável ({window_label}), deve entrar no briefing como opção de alternante/desvio.",
            "Rever adequacy, minima e utilidade real do alternante/desvio.",
        )

    return (
        "P2",
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


def _extract_weather_threats_from_airport_block(
    airport: str,
    lines: list[str],
    page_number: int,
    ctx: dict,
) -> list[Threat]:
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
        if not _line_has_weather_threat(line):
            continue

        start, end = _parse_taf_group_window(line)

        if start is None or end is None:
            if line.startswith("SA "):
                start, end = app_start, app_end
            else:
                continue

        start, end = _align_window_to_reference(start, end, app_start)

        if not _time_overlap_minutes(start, end, app_start, app_end):
            continue

        priority, category, title, why, expected_action = _classify_weather_line(line, airport, window_label)

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

        # MEL / CDL
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

        # Callsign with appended letter
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

        # Oceanic / ETOPS awareness
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

        # Weather List v6 parser
        if "airport weather list" in full_lower or "destination:" in full_lower or "departure:" in full_lower:
            airport_blocks = _build_airport_weather_blocks(lines)
            for airport, airport_lines in airport_blocks.items():
                raw_threats.extend(
                    _extract_weather_threats_from_airport_block(
                        airport=airport,
                        lines=airport_lines,
                        page_number=pnum,
                        ctx=ctx,
                    )
                )

        # Navigation / GNSS / interference
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

        # Runway / procedure / navaid limitation
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

    # Deduplicate / consolidate
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
