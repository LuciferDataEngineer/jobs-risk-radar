"""Draw the regions map from the local boundary file.

The shapes are the map. A tile server is not used: the previous CARTO
basemap answered keyless requests with an "API KEY REQUIRED" watermark,
and a Leaflet map created inside a hidden tab fitted Australia at the
tile layer's maximum zoom, so the page showed one orange square.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping

from jrr.paths import boundary_path

TONE_COLOURS = {
    "high": "#9f1239",
    "watch": "#c2410c",
    "steady": "#d6d3c4",
    "easier": "#0f766e",
}
NEUTRAL = "#e7e1d6"
_SPAN = 1000.0


def region_svg(regions: Iterable[Mapping], boundary: Mapping | None = None) -> str:
    """Inline SVG of every SA4, fitted to Australia, coloured by outlook."""
    geo = boundary if boundary is not None else _load_boundary()
    by_code = {str(row["code"]): row for row in regions}
    placed = []
    for feature in geo["features"]:
        code = str(feature["properties"].get("radar_code", ""))
        projected = [
            [_mercator(lon, lat) for lon, lat in ring]
            for ring in _rings(feature["geometry"])
        ]
        points = [point for ring in projected for point in ring]
        if len(points) < 3:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        placed.append({"code": code, "rings": projected, "area": area})

    xs = [point[0] for item in placed for ring in item["rings"] for point in ring]
    ys = [point[1] for item in placed for ring in item["rings"] for point in ring]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    scale = _SPAN / max(width, height)
    pad = round(_SPAN * 0.025)
    view_w = round(width * scale) + pad * 2
    view_h = round(height * scale) + pad * 2

    def locate(point: tuple[float, float]) -> tuple[int, int]:
        x = round((point[0] - min_x) * scale) + pad
        # Screen y grows downward; north stays toward the top of the map.
        y = round((max_y - point[1]) * scale) + pad
        return x, y

    paths = []
    for item in sorted(placed, key=lambda row: (-row["area"], row["code"])):
        row = by_code.get(item["code"])
        colour = TONE_COLOURS.get(row["tone"], NEUTRAL) if row else NEUTRAL
        drawing = _path_d(item["rings"], locate)
        if not drawing:
            continue
        label = _xml(_label(row) if row else item["code"])
        code = _xml(item["code"])
        paths.append(
            f'<path data-code="{code}" fill="{colour}" d="{drawing}" '
            f'tabindex="0" aria-label="{label}"/>'
        )

    joined = "".join(paths)
    return (
        f'<svg viewBox="0 0 {view_w} {view_h}" role="group" '
        f'aria-label="Australian regions coloured by the outlook from September to December">'
        f"{joined}</svg>"
    )


def _load_boundary() -> dict:
    return json.loads(boundary_path().read_text(encoding="utf-8"))


def _mercator(lon: float, lat: float) -> tuple[float, float]:
    clamped = min(max(lat, -85.0), 85.0)
    x = math.radians(lon)
    y = math.log(math.tan(math.pi / 4 + math.radians(clamped) / 2))
    return x, y


def _rings(geometry: Mapping) -> list[list[tuple[float, float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    polygons = coordinates if kind == "MultiPolygon" else [coordinates]
    rings = []
    for polygon in polygons:
        for ring in polygon:
            if len(ring) >= 4:
                rings.append([(float(point[0]), float(point[1])) for point in ring])
    return rings


def _path_d(rings: list[list[tuple[float, float]]], locate) -> str:
    chunks = []
    for ring in rings:
        points = []
        for lon_lat in ring:
            point = locate(lon_lat)
            if not points or points[-1] != point:
                points.append(point)
        if points and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 3:
            continue
        move = f"M{points[0][0]} {points[0][1]}"
        lines = "".join(f"L{x} {y}" for x, y in points[1:])
        chunks.append(f"{move}{lines}Z")
    return "".join(chunks)


def _label(row: Mapping) -> str:
    since = float(row["since_june"])
    signed = f"+{since:.1f}" if since > 0 else f"{since:.1f}"
    rate = float(row["rate"])
    return (
        f"{row['name']}. {rate:.1f}% now, {signed} since June. "
        f"{row['outlook']} ({row['sure']})"
    )


def _xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
