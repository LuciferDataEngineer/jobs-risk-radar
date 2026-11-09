import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from jrr.choropleth import NEUTRAL, TONE_COLOURS, region_svg
from jrr.paths import boundary_path, root

# Status colours on the dark briefing. High, watch and easier are bright enough
# to read on a near-black page; steady stays a light neutral. A change here is
# a change to the briefing, not a casual repaint.
LEGEND = {
    "high": "#fb7185",
    "watch": "#fb923c",
    "steady": "#d6d3c4",
    "easier": "#2dd4bf",
}
TILE_MARKERS = (
    "basemaps.cartocdn.com",
    "cartocdn",
    "tile.openstreetmap.org",
    "api.mapbox.com",
    "maps.googleapis.com",
    "stadiamaps",
    "leaflet",
    "L.tileLayer",
    "L.geoJSON",
    "api_key",
    "apikey",
    "API KEY",
    "{z}/{x}/{y}",
)


def test_palette_matches_the_legend():
    assert TONE_COLOURS == LEGEND


def test_projection_puts_north_above_south_and_west_left_of_east():
    svg = region_svg(
        [
            _row("N", "steady"),
            _row("S", "watch"),
            _row("W", "easier"),
            _row("E", "high"),
        ],
        {
            "type": "FeatureCollection",
            "features": [
                _box("N", 130, -12, 131, -13),
                _box("S", 147, -42, 148, -43),
                _box("W", 115, -34, 116, -35),
                _box("E", 153, -31, 154, -32),
            ],
        },
    )
    centres = _centres(svg)
    assert centres["N"][1] < centres["S"][1]
    assert centres["W"][0] < centres["E"][0]
    fills = {path.attrib["data-code"]: path.attrib["fill"] for path in _paths(svg)}
    assert fills == {"N": LEGEND["steady"], "S": LEGEND["watch"], "W": LEGEND["easier"], "E": LEGEND["high"]}


def test_unknown_region_is_still_drawn():
    svg = region_svg([], {"type": "FeatureCollection", "features": [_box("999", 140, -30, 141, -31)]})
    path = _paths(svg)[0]
    assert path.attrib["fill"] == NEUTRAL
    assert path.attrib["data-code"] == "999"
    assert len(_pairs(path.attrib["d"])) >= 3


def test_shipped_map_draws_every_region_without_a_tile_service():
    html = Path(root() / "site" / "index.html").read_text(encoding="utf-8")
    lowered = html.lower()
    for marker in TILE_MARKERS:
        assert marker.lower() not in lowered, marker
    assert "fetch(\"sa4.geojson\")" not in html
    assert "fitBounds" not in html
    assert "invalidateSize" not in html

    payload = json.loads(_radar(html))
    boundary = json.loads(boundary_path().read_text(encoding="utf-8"))
    svg = _svg(html)
    paths = _paths_element(svg)
    by_code = {path.attrib["data-code"]: path for path in paths}
    region_codes = [str(row["code"]) for row in payload["regions"]]
    boundary_codes = [str(feature["properties"]["radar_code"]) for feature in boundary["features"]]

    assert len(paths) == len(region_codes) == len(boundary_codes) == 87
    assert set(by_code) == set(region_codes) == set(boundary_codes)

    view_x, view_y, view_w, view_h = [float(part) for part in svg.attrib["viewBox"].split()]
    all_x = []
    all_y = []
    for row in payload["regions"]:
        path = by_code[str(row["code"])]
        assert path.attrib["fill"] == LEGEND[row["tone"]]
        label = path.attrib["aria-label"]
        since = float(row["since_june"])
        signed = f"+{since:.1f}" if since > 0 else f"{since:.1f}"
        assert row["name"] in label
        assert f"{float(row['rate']):.1f}%" in label
        assert signed in label
        assert row["outlook"] in label
        assert row["sure"] in label
        pairs = _pairs(path.attrib["d"])
        assert len(pairs) >= 3
        all_x.extend(point[0] for point in pairs)
        all_y.extend(point[1] for point in pairs)

    # The whole country is in the initial view. A hidden-tab fit used to leave
    # the view on one interior patch, so the shapes were off the screen.
    assert max(all_x) - min(all_x) > view_w * 0.9
    assert max(all_y) - min(all_y) > view_h * 0.9
    assert view_x - 1 <= min(all_x) and max(all_x) <= view_x + view_w + 1
    assert view_y - 1 <= min(all_y) and max(all_y) <= view_y + view_h + 1
    assert view_w > view_h

    centres = {
        path.attrib["data-code"]: _centroid(path.attrib["d"])
        for path in paths
    }
    assert centres["701"][1] < centres["603"][1]  # Darwin north of Tasmania's South East
    assert centres["501"][0] < centres["108"][0]  # Bunbury west of the Mid North Coast

    for tone, colour in LEGEND.items():
        assert f"background:{colour}" in html, tone
    assert 'id="map-zoom-in"' in html
    assert 'id="map-zoom-out"' in html
    assert 'id="map-tip"' in html
    assert "pointerover" in html
    assert 'id="national"' in html and 'id="bars"' in html and 'id="states"' in html
    assert "Chart.getChart" in html
    assert "Unemployment is already higher than a year ago" in html
    assert payload["headlines"]["rising_name"] == "Darwin"


def _row(code: str, tone: str) -> dict:
    return {
        "code": code,
        "name": code,
        "rate": 4.0,
        "since_june": 0.2,
        "outlook": "looks steady",
        "sure": "less sure",
        "tone": tone,
    }


def _box(code: str, west: float, north: float, east: float, south: float) -> dict:
    ring = [[west, north], [east, north], [east, south], [west, south], [west, north]]
    return {
        "type": "Feature",
        "properties": {"radar_code": code},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


def _radar(html: str) -> str:
    match = re.search(r'<script id="radar" type="application/json">(.*?)</script>', html)
    assert match, "embedded briefing missing"
    return match.group(1)


def _svg(html: str) -> ET.Element:
    match = re.search(r"<svg\b.*?</svg>", html)
    assert match, "region map missing"
    return ET.fromstring(match.group(0))


def _paths(svg: str) -> list[ET.Element]:
    return _paths_element(ET.fromstring(svg))


def _paths_element(svg: ET.Element) -> list[ET.Element]:
    return [element for element in svg if element.tag == "path"]


def _pairs(drawing: str) -> list[tuple[float, float]]:
    numbers = [float(item) for item in re.findall(r"-?\d+(?:\.\d+)?", drawing)]
    return list(zip(numbers[0::2], numbers[1::2], strict=True))


def _centroid(drawing: str) -> tuple[float, float]:
    pairs = _pairs(drawing)
    return (sum(point[0] for point in pairs) / len(pairs), sum(point[1] for point in pairs) / len(pairs))


def _centres(svg: str) -> dict[str, tuple[float, float]]:
    return {path.attrib["data-code"]: _centroid(path.attrib["d"]) for path in _paths(svg)}
