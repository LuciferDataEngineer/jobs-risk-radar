"""Stakeholder pages. Plain language only; the technical record lives in the README."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import polars as pl

from jrr.choropleth import TONE_COLOURS, region_svg
from jrr.paths import boundary_path, report_dir, site_dir, snapshot_dir

MELBOURNE = ZoneInfo("Australia/Melbourne")


def build_site(scores: pd.DataFrame, summary: dict) -> dict:
    payload = _payload(scores, summary)
    site = site_dir()
    site.mkdir(parents=True, exist_ok=True)
    (site / ".nojekyll").write_text("")
    shutil.copyfile(boundary_path(), site / "sa4.geojson")
    html = _page(payload)
    (site / "index.html").write_text(html)
    (report_dir() / "headlines.json").write_text(json.dumps(payload["headlines"], indent=2) + "\n")
    return payload["headlines"]


def _payload(scores: pd.DataFrame, summary: dict) -> dict:
    scores = scores.copy()
    scores["people"] = (scores["labour_force"] * 1000).round().astype(int)
    scores["outlook"], scores["sure"] = zip(*scores.apply(_words, axis=1), strict=True)
    scores["tone"] = [
        _tone_for(float(change), float(excess))
        for change, excess in zip(scores["predicted_change"], scores["excess"], strict=True)
    ]
    rising = scores[scores["predicted_change"] >= 0.1].sort_values(
        "predicted_change", ascending=False
    )
    already = scores[scores["delta_3"] >= 0.5]
    sharp = scores.sort_values("delta_3", ascending=False).iloc[0]
    rise_context = _june_to_september()
    national = _national()
    states = _states()
    backtest = summary["backtest"]
    hit_of_10 = int(round((backtest.get("top10_hit_rate") or 0) * 10))
    generated = datetime.now(MELBOURNE).strftime("%-d %b %Y, %-I:%M %p %Z")
    headlines = {
        "regions": int(len(scores)),
        "rising": int(len(rising)),
        "rising_name": str(rising.iloc[0]["sa4_name"]) if len(rising) else "",
        "rising_state": str(rising.iloc[0]["state_name"]) if len(rising) else "",
        "rising_rate": float(rising.iloc[0]["unemp_rate"]) if len(rising) else None,
        "rising_change": float(rising.iloc[0]["predicted_change"]) if len(rising) else None,
        "already": int(len(already)),
        "already_people": int(already["people"].sum()),
        "sharp_name": str(sharp["sa4_name"]),
        "sharp_state": str(sharp["state_name"]),
        "sharp_now": float(sharp["unemp_rate"]),
        "sharp_since": float(sharp["delta_3"]),
        "typical_since_june": rise_context["this_year"],
        "typical_prior": rise_context["prior_max"],
        "easing": int((scores["predicted_change"] < -0.1).sum()),
        "national_rate": national["latest"],
        "national_year_ago": national["year_ago"],
        "cash_rate": summary["cash_adjustment"]["cash_rate"],
        "hikes_2026": _hikes_2026(),
        "hit_of_10": hit_of_10,
        "closer_than_last_year": backtest["mae_model"] <= backtest["mae_usual_pace"],
        "generated": generated,
    }
    headlines["copy"] = _copy(headlines, scores)
    tone_rank = {"high": 0, "watch": 1, "steady": 2, "easier": 3}
    scores = scores.assign(rank=scores["tone"].map(tone_rank)).sort_values(
        ["rank", "delta_3"], ascending=[True, False]
    )
    regions = [_region_row(row) for row in scores.itertuples(index=False)]
    already_chart = [
        _region_row(row)
        for row in scores.sort_values("delta_3", ascending=False).head(8).itertuples(index=False)
    ]
    return {
        "headlines": headlines,
        "regions": regions,
        "national_series": national["series"],
        "states": states,
        "already_chart": already_chart,
    }


def _region_row(row) -> dict:
    return {
        "code": row.sa4_code,
        "name": row.sa4_name,
        "state": row.state_name,
        "rate": round(float(row.unemp_rate), 1),
        "change": round(float(row.predicted_change), 1),
        "since_june": round(float(row.delta_3), 1),
        "outlook": row.outlook,
        "sure": row.sure,
        "tone": row.tone,
        "people": int(row.people),
    }


def _copy(headlines: dict, scores: pd.DataFrame) -> dict:
    rising = headlines["rising_name"] or "one region"
    closer = (
        "Checked on past quarters, this outlook was closer to what happened than simply repeating last year's move."
        if headlines["closer_than_last_year"]
        else "Checked on past quarters, repeating last year's move was as close or closer. Treat the ordering as a guide."
    )
    weak_relief = scores[
        scores["outlook"].str.contains("less than last year", na=False)
        & (scores["unemp_rate"] >= 5)
    ]
    weak_names = _and_join(
        weak_relief.sort_values("unemp_rate", ascending=False)["sa4_name"].head(3)
    )
    jumped = scores.sort_values("delta_3", ascending=False).head(3)
    jumped_names = _and_join(jumped["sa4_name"])
    high_now = scores[scores["unemp_rate"] >= 6].sort_values("unemp_rate", ascending=False)
    high_names = _and_join(high_now["sa4_name"].head(4))
    return {
        "lede": (
            f"Unemployment is already higher than a year ago. "
            f"From June to September the typical region rose {headlines['typical_since_june']:.1f} points, "
            f"more than in any of the previous three years. "
            f"By December the rate is expected to ease in {headlines['easing']} of {headlines['regions']} regions. "
            f"{rising} is the place still expected to rise."
        ),
        "meaning": [
            (
                f"The official unemployment rate is {headlines['national_rate']:.1f}%, "
                f"up from {headlines['national_year_ago']:.1f}% a year ago. "
                f"The cash rate target is {headlines['cash_rate']:.2f}% after { _hike_phrase(headlines['hikes_2026']) } this year."
            ),
            (
                f"{headlines['sharp_name']} has seen the sharpest recent rise, "
                f"up {headlines['sharp_since']:.1f} points since June to {headlines['sharp_now']:.1f}%. "
                f"{headlines['already']} regions are up by half a point or more. "
                f"In 2023, 2024 and 2025 the typical region moved by about "
                f"{headlines['typical_prior']:.1f} points or less over those same months."
            ),
            (
                f"The next three months usually bring some relief, and that is still the expectation almost everywhere. "
                f"{rising} is the exception"
                + (
                    f", with the rate expected to be about {headlines['rising_change']:.1f} points higher than the {headlines['rising_rate']:.1f}% recorded in September."
                    if headlines["rising_change"] is not None
                    else "."
                )
                + f" When past outlooks named 10 regions, about {headlines['hit_of_10']} of them really were among the 10 that moved the most. {closer}"
            ),
        ],
        "actions": [
            f"Put extra help now into {jumped_names}. These are the regions where unemployment has already jumped since June.",
            f"Keep a close watch on {rising}. It is the region where the rate is still expected to be higher in December, even though it is low today.",
            (
                f"In {weak_names}, do not assume the usual end-of-year improvement will clear a high rate. The easing looks smaller than last year."
                if weak_names
                else "Do not assume every high rate will fall away by Christmas."
            ),
            (
                f"Rates are already above 6% in {high_names}. A softer December does not remove the need for support there now."
                if high_names
                else "Keep routine services running everywhere else."
            ),
        ],
        "line_insight": (
            f"The official rate was {headlines['national_rate']:.1f}% in September, "
            f"from {headlines['national_year_ago']:.1f}% a year earlier."
        ),
        "state_insight": "Victoria is the highest of these state figures. The Northern Territory and the ACT are not in this table.",
        "bar_insight": "Points added to the unemployment rate from June to September 2026. This lift is larger than the same three months in recent years.",
    }


def _and_join(names) -> str:
    items = [str(name) for name in names]
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def _hike_phrase(count: int) -> str:
    words = {5: "five increases"}
    return words.get(count, f"{count} increases")


def _words(row: pd.Series) -> tuple[str, str]:
    change = float(row["predicted_change"])
    excess = float(row["excess"])
    chance = float(row["rise_chance"])
    sure = "fairly sure" if chance >= 0.55 or chance <= 0.2 else "less sure"
    if change >= 0.1:
        return "likely to rise", "less sure" if chance < 0.5 else "fairly sure"
    if abs(change) < 0.1 and excess >= 0.25:
        return "looks steady, with less of a fall than last year", "less sure"
    if abs(change) < 0.1:
        return "looks steady", "less sure"
    if excess >= 0.35:
        return "should ease, but by less than last year", "less sure"
    if change <= -0.45:
        return "should ease", sure
    return "should ease, much like last year", "less sure"


def _tone_for(change: float, excess: float) -> str:
    if change >= 0.1:
        return "high"
    if abs(change) < 0.1 or excess >= 0.35:
        return "watch"
    if change <= -0.45 and excess < 0.2:
        return "easier"
    return "steady"


def _national() -> dict:
    frame = pl.read_parquet(snapshot_dir() / "state_unemployment.parquet")
    series = frame.filter(pl.col("region_code") == "AUS").sort("month")
    latest_row = series.row(-1, named=True)
    year_ago = series.filter(pl.col("month") <= pl.date(2025, 9, 1)).row(-1, named=True)
    window = series.filter(pl.col("month") >= pl.date(2023, 1, 1))
    points = [
        {"month": str(month)[:7], "rate": round(float(rate), 2)}
        for month, rate in zip(window["month"].to_list(), window["unemp_rate_sa"].to_list(), strict=True)
    ]
    return {
        "latest": round(float(latest_row["unemp_rate_sa"]), 1),
        "year_ago": round(float(year_ago["unemp_rate_sa"]), 1),
        "series": points,
    }


def _states() -> list[dict]:
    frame = pl.read_parquet(snapshot_dir() / "state_unemployment.parquet")
    rows = []
    for code, name in [
        ("1", "New South Wales"),
        ("2", "Victoria"),
        ("3", "Queensland"),
        ("4", "South Australia"),
        ("5", "Western Australia"),
        ("6", "Tasmania"),
    ]:
        part = frame.filter(pl.col("region_code") == code).sort("month")
        now = part.row(-1, named=True)
        then = part.filter(pl.col("month") <= pl.date(2025, 9, 1)).row(-1, named=True)
        rows.append(
            {
                "name": name,
                "now": round(float(now["unemp_rate_sa"]), 1),
                "then": round(float(then["unemp_rate_sa"]), 1),
            }
        )
    return rows


def _june_to_september() -> dict:
    frame = pl.read_parquet(snapshot_dir() / "sa4_month.parquet").with_columns(
        pl.col("month").cast(pl.Date)
    )
    medians = []
    for year in (2023, 2024, 2025, 2026):
        june = frame.filter(pl.col("month") == pl.date(year, 6, 1)).select(
            "sa4_code", pl.col("unemp_rate").alias("june")
        )
        september = frame.filter(pl.col("month") == pl.date(year, 9, 1)).select(
            "sa4_code", pl.col("unemp_rate").alias("september")
        )
        change = june.join(september, on="sa4_code").select(
            (pl.col("september") - pl.col("june")).alias("delta")
        )
        medians.append((year, float(change["delta"].median())))
    prior = max(value for year, value in medians if year < 2026)
    this_year = next(value for year, value in medians if year == 2026)
    return {"this_year": round(this_year, 1), "prior_max": round(prior, 1)}


def _hikes_2026() -> int:
    cash = pl.read_parquet(snapshot_dir() / "cash_rate_month.parquet").sort("month")
    year = cash.filter(pl.col("month") >= pl.datetime(2026, 1, 1))
    values = year["cash_rate_target"].to_list()
    return int(sum(1 for previous, current in zip(values, values[1:], strict=False) if current > previous))


def _legend_html() -> str:
    labels = (
        ("high", "Likely to rise"),
        ("watch", "Little relief, or less than last year"),
        ("steady", "Should ease"),
        ("easier", "A clearer easing"),
    )
    return "".join(
        f'<span><i class="swatch" style="background:{TONE_COLOURS[tone]}"></i>{label}</span>'
        for tone, label in labels
    )


def _page(payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    svg = region_svg(payload["regions"])
    tones = "\n".join(f"  --{name}: {colour};" for name, colour in TONE_COLOURS.items())
    return (
        PAGE.replace("/*__DATA__*/null", data)
        .replace("<!--__MAP__-->", svg)
        .replace("<!--__LEGEND__-->", _legend_html())
        .replace("/*__TONES__*/", tones)
    )


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0c0c0e">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' rx='3' fill='%2360a5fa'/%3E%3C/svg%3E">
<title>Jobs Risk Radar</title>
<style>
:root {
/*__TONES__*/
  --bg: #0c0c0e;
  --card: #17171a;
  --line: #2c2c31;
  --line-strong: #3a3a40;
  --text: #f4f4f5;
  --muted: #a1a1aa;
  --blue: #60a5fa;
  --orange: #fb923c;
  --focus: #93c5fd;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  margin: 0;
  color: var(--text);
  background: var(--bg);
  font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
.shell { width: min(1120px, calc(100% - 40px)); margin: 0 auto; }
.topbar { border-bottom: 1px solid var(--line); }
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 52px;
}
.brand { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; min-width: 0; }
h1.product { margin: 0; font-size: 14px; font-weight: 600; letter-spacing: 0; }
.updated { margin: 0; color: var(--muted); font-size: 13px; }
a.github { color: var(--blue); font-size: 14px; font-weight: 600; text-decoration: none; white-space: nowrap; }
a.github:hover { text-decoration: underline; }
nav.tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  border-bottom: 1px solid var(--line);
}
nav.tabs button {
  appearance: none;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  padding: 12px 14px 10px;
  margin-bottom: -1px;
  cursor: pointer;
  white-space: nowrap;
}
nav.tabs button:hover { color: var(--text); }
nav.tabs button[aria-selected="true"] {
  color: var(--text);
  border-bottom-color: var(--text);
}
main { padding: 28px 0 56px; }
h2.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.2;
}
.section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 16px;
}
.lede { margin: 12px 0 0; max-width: 72ch; font-size: 16px; color: var(--text); }
.sub { margin: 8px 0 0; max-width: 72ch; color: var(--muted); font-size: 14px; }
.links { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; margin: 14px 0 22px; }
.links a { color: #e4e4e7; font-size: 14px; text-underline-offset: 3px; }
.links span { color: var(--muted); }
.filter {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  position: relative;
  background: #222226;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  padding: 6px 28px 6px 14px;
  color: var(--text);
  font-size: 13px;
  max-width: 100%;
}
.filter-key { color: var(--muted); }
.filter select {
  appearance: none;
  background: transparent;
  border: 0;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  font-size: 13px;
  padding: 0;
  margin: 0;
  cursor: pointer;
  max-width: 220px;
}
.filter::after {
  content: "";
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-30%);
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid var(--muted);
  pointer-events: none;
}
.filter:focus-within { outline: 2px solid var(--focus); outline-offset: 2px; }
.filter select:focus { outline: none; }
section.panel { display: none; }
section.panel.active { display: block; }
.block-title { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  gap: 12px;
  margin: 0 0 16px;
}
.kpi {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px 18px 14px;
  min-width: 0;
}
.kpi .label { margin: 0 0 10px; color: var(--muted); font-size: 13px; }
.kpi .value {
  margin: 0;
  color: #fafafa;
  font-size: clamp(32px, 4vw, 42px);
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.05;
  font-variant-numeric: tabular-nums;
  overflow-wrap: break-word;
}
.kpi .value.compact { font-size: 26px; line-height: 1.2; letter-spacing: -0.02em; }
.kpi .note { margin: 8px 0 0; color: var(--muted); font-size: 13px; line-height: 1.4; }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 16px 18px 14px;
  margin-top: 16px;
}
.card h3 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }
.chart-wrap { position: relative; height: 280px; width: 100%; }
.chart-wrap.tall { height: 440px; }
.footnote { margin: 10px 0 0; color: var(--muted); font-size: 13px; max-width: 75ch; }
.prose p { margin: 0 0 12px; max-width: 75ch; color: #e4e4e7; }
.prose p:last-child { margin-bottom: 0; }
.actions { display: grid; gap: 12px; }
.action p { margin: 0; max-width: 75ch; }
.action .label { margin: 0 0 6px; color: var(--muted); font-size: 13px; }
#map {
  position: relative;
  height: min(640px, 70vw);
  min-height: 320px;
  border-radius: 10px;
  overflow: hidden;
  background: #0e141c;
  border: 1px solid var(--line);
  touch-action: none;
}
#map svg { width: 100%; height: 100%; display: block; cursor: grab; }
#map svg:active { cursor: grabbing; }
#map path {
  stroke: rgba(244, 244, 245, 0.55);
  stroke-width: 1.15;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}
#map path:hover, #map path:focus { stroke: #ffffff; stroke-width: 2.4; outline: none; }
#map path.dim { opacity: 0.16; }
#map path.dim:hover, #map path.dim:focus { opacity: 0.7; }
.map-controls {
  position: absolute;
  z-index: 2;
  top: 10px;
  left: 10px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  overflow: hidden;
}
.map-controls button {
  width: 34px;
  height: 34px;
  border: 0;
  border-bottom: 1px solid var(--line);
  background: #222226;
  color: var(--text);
  font: 600 18px/1 inherit;
  cursor: pointer;
}
.map-controls button:last-child { border-bottom: 0; }
.map-controls button:hover, .map-controls button:focus { background: #2c2c31; }
.map-tip {
  position: absolute;
  z-index: 3;
  margin: 0;
  max-width: 240px;
  padding: 8px 10px;
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  background: #141418;
  color: var(--text);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.45);
  font-size: 14px;
  line-height: 1.35;
  pointer-events: none;
}
.legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-top: 12px; font-size: 13px; color: #d4d4d8; }
.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: -1px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28);
}
details.exact { margin-top: 12px; border-top: 1px solid var(--line); padding-top: 4px; }
details.exact summary {
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #d4d4d8;
  font-size: 14px;
  padding: 8px 0;
}
details.exact summary::-webkit-details-marker { display: none; }
details.exact summary::before {
  content: "";
  width: 0;
  height: 0;
  border-left: 5px solid #d4d4d8;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
}
details.exact[open] summary::before { transform: rotate(90deg); }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.toolbar h3 { margin: 0; }
input[type="search"] {
  width: min(320px, 100%);
  font: inherit;
  font-size: 14px;
  color: var(--text);
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--line-strong);
  background: #111113;
}
input[type="search"]::placeholder { color: var(--muted); }
.table-scroll { overflow-x: auto; }
.table-scroll.bounded { max-height: 560px; overflow: auto; }
.table-scroll.bounded table { min-width: 640px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
th {
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}
.table-scroll.bounded th { position: sticky; top: 0; background: var(--card); z-index: 1; }
tbody tr:hover td { background: rgba(255, 255, 255, 0.03); }
.where { color: var(--muted); }
.pill { font-weight: 600; }
.pill.high { color: var(--high); }
.pill.watch { color: var(--watch); }
.pill.steady { color: var(--steady); }
.pill.easier { color: var(--easier); }
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
footer.sources {
  margin-top: 28px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 13px;
}
footer.sources a { color: var(--focus); }
@media (max-width: 640px) {
  .shell { width: min(1120px, calc(100% - 28px)); }
  .bar { align-items: flex-start; padding: 10px 0; }
  .brand { flex-direction: column; align-items: flex-start; gap: 2px; }
  nav.tabs { margin: 0 -14px; padding: 0 6px; }
  nav.tabs button {
    flex: 1 1 0;
    min-width: 0;
    padding: 10px 4px 8px;
    font-size: 12px;
    text-align: center;
    white-space: normal;
    line-height: 1.25;
  }
  h2.page-title { font-size: 24px; }
  .chart-wrap { height: 240px; }
  .chart-wrap.tall { height: 520px; }
  main { padding-top: 22px; }
  .kpi .value.compact { font-size: 22px; }
}
@media (prefers-reduced-motion: reduce) {
  details.exact summary::before { transition: none; }
}
</style>
</head>
<body>
<header class="topbar">
  <div class="shell bar">
    <div class="brand">
      <h1 class="product">Jobs Risk Radar</h1>
      <p class="updated" id="updated"></p>
    </div>
    <a class="github" href="https://github.com/LuciferDataEngineer/jobs-risk-radar">GitHub</a>
  </div>
</header>
<div class="shell">
  <nav class="tabs" role="tablist" aria-label="Briefing">
    <button type="button" role="tab" id="tab-overview" aria-controls="overview" aria-selected="true">Overview</button>
    <button type="button" role="tab" id="tab-map" aria-controls="map-panel" aria-selected="false">Regions map</button>
    <button type="button" role="tab" id="tab-risk" aria-controls="risk" aria-selected="false">Who's at risk</button>
    <button type="button" role="tab" id="tab-do" aria-controls="do" aria-selected="false">What to do</button>
  </nav>
</div>
<main class="shell">
  <p id="filter-status" class="visually-hidden" aria-live="polite"></p>
  <section id="overview" class="panel active" role="tabpanel" aria-labelledby="overview-title">
    <h2 id="overview-title" class="page-title">The next three months</h2>
    <p class="lede" id="lede"></p>
    <p class="sub" id="period"></p>
    <p class="links">
      <a href="#map-panel" data-tab="map-panel">Regions map</a>
      <span aria-hidden="true">·</span>
      <a href="#risk" data-tab="risk">Who's at risk</a>
      <span aria-hidden="true">·</span>
      <a href="#do" data-tab="do">What to do</a>
      <span aria-hidden="true">·</span>
      <a href="#sources">Sources</a>
    </p>
    <h3 class="block-title">The latest figures</h3>
    <div class="kpis" id="kpis"></div>
    <article class="card">
      <h3>Unemployment has already climbed</h3>
      <div class="chart-wrap"><canvas id="national" aria-label="Official unemployment rate from January 2023 to September 2026"></canvas></div>
      <p class="footnote" id="line-insight"></p>
      <details class="exact">
        <summary>Exact chart values</summary>
        <div id="national-exact"></div>
      </details>
    </article>
    <article class="card prose" id="meaning"></article>
  </section>
  <section id="map-panel" class="panel" role="tabpanel" aria-labelledby="map-title">
    <div class="section-head">
      <h2 id="map-title" class="page-title">Regions map</h2>
      <label class="filter">
        <span class="filter-key">State</span>
        <select class="state-filter" aria-label="Filter the map and the region list by state">
          <option value="">All states</option>
        </select>
      </label>
    </div>
    <p class="sub">Colour shows the outlook from September to December. Hover or tap a region for the rate today and what the next three months look like.</p>
    <p class="links">
      <a href="#overview" data-tab="overview">Overview</a>
      <span aria-hidden="true">·</span>
      <a href="#risk" data-tab="risk">Who's at risk</a>
      <span aria-hidden="true">·</span>
      <a href="#do" data-tab="do">What to do</a>
      <span aria-hidden="true">·</span>
      <a href="#sources">Sources</a>
    </p>
    <article class="card">
      <div id="map">
        <!--__MAP__-->
        <div class="map-controls">
          <button type="button" id="map-zoom-in" aria-label="Zoom in">+</button>
          <button type="button" id="map-zoom-out" aria-label="Zoom out">−</button>
        </div>
        <p id="map-tip" class="map-tip" hidden></p>
      </div>
      <div class="legend"><!--__LEGEND__--></div>
      <p class="footnote">Western Australia's two remote outback regions are drawn together, matching the published figures. Borders are simplified.</p>
      <details class="exact">
        <summary>Exact map values</summary>
        <div id="map-exact"></div>
      </details>
    </article>
  </section>
  <section id="risk" class="panel" role="tabpanel" aria-labelledby="risk-title">
    <div class="section-head">
      <h2 id="risk-title" class="page-title">Who's at risk</h2>
      <label class="filter">
        <span class="filter-key">State</span>
        <select class="state-filter" aria-label="Filter the map and the region list by state">
          <option value="">All states</option>
        </select>
      </label>
    </div>
    <p class="sub">Where unemployment has already jumped since June, and how the states compare with a year ago.</p>
    <p class="links">
      <a href="#overview" data-tab="overview">Overview</a>
      <span aria-hidden="true">·</span>
      <a href="#map-panel" data-tab="map-panel">Regions map</a>
      <span aria-hidden="true">·</span>
      <a href="#do" data-tab="do">What to do</a>
      <span aria-hidden="true">·</span>
      <a href="#sources">Sources</a>
    </p>
    <article class="card">
      <h3 id="bar-title">Where the jobless rate has already jumped</h3>
      <div class="chart-wrap tall"><canvas id="bars" aria-label="Points added to the unemployment rate from June to September 2026"></canvas></div>
      <p class="footnote" id="bar-insight"></p>
      <details class="exact">
        <summary>Exact chart values</summary>
        <div id="bars-exact"></div>
      </details>
    </article>
    <article class="card">
      <h3>The states, one year apart</h3>
      <div class="chart-wrap"><canvas id="states" aria-label="Official unemployment rate by state, September 2025 and September 2026"></canvas></div>
      <p class="footnote" id="state-insight"></p>
      <details class="exact">
        <summary>Exact chart values</summary>
        <div id="states-exact"></div>
      </details>
    </article>
    <article class="card">
      <div class="toolbar">
        <h3>Every region</h3>
        <input id="find" type="search" placeholder="Find a region or state" aria-label="Find a region" autocomplete="off">
      </div>
      <div class="table-scroll bounded">
        <table>
          <caption class="visually-hidden">Every region, the rate now, the change since June, and the outlook to December</caption>
          <thead>
            <tr><th>Region</th><th>Now</th><th>Since June</th><th>By December</th></tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </article>
  </section>
  <section id="do" class="panel" role="tabpanel" aria-labelledby="do-title">
    <h2 id="do-title" class="page-title">What to do before Christmas</h2>
    <p class="sub">Where to put extra help now, and where a softer December is not enough.</p>
    <p class="links">
      <a href="#overview" data-tab="overview">Overview</a>
      <span aria-hidden="true">·</span>
      <a href="#map-panel" data-tab="map-panel">Regions map</a>
      <span aria-hidden="true">·</span>
      <a href="#risk" data-tab="risk">Who's at risk</a>
      <span aria-hidden="true">·</span>
      <a href="#sources">Sources</a>
    </p>
    <div class="actions" id="actions"></div>
  </section>
  <footer class="sources" id="sources">
    <p>Sources: Australian Bureau of Statistics, Regional Labour Force, September 2026 (modelled regional rates) and Labour Force, Australia, September 2026 (official state and national rates); ABS Job Vacancies and Building Approvals; Reserve Bank of Australia cash rate target. Region boundaries from the ABS, simplified for this map. All ABS material is free to reuse with credit (CC BY 4.0). Prepared <span id="stamp"></span>. This is an independent briefing, not a government site. Rates are rounded to one decimal place.</p>
  </footer>
</main>
<script id="radar" type="application/json">/*__DATA__*/null</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script>
const data = JSON.parse(document.getElementById("radar").textContent);
const h = data.headlines;
let currentState = "";

document.getElementById("lede").textContent = h.copy.lede;
document.getElementById("period").textContent = "Regional figures are for September 2026, the latest release. The outlook runs to December 2026. The cash rate target of " + h.cash_rate.toFixed(2) + "% is the rate in force now. A point is a percentage point of the unemployment rate.";
document.getElementById("updated").textContent = "Updated " + h.generated;
document.getElementById("stamp").textContent = h.generated;
document.getElementById("line-insight").textContent = h.copy.line_insight;
document.getElementById("state-insight").textContent = h.copy.state_insight;

const kpis = document.getElementById("kpis");
[
  [h.national_rate.toFixed(1) + "%", "Unemployment in Australia", "up from " + h.national_year_ago.toFixed(1) + "% a year ago"],
  ["+" + h.typical_since_june.toFixed(1), "Typical rise since June", "points, versus about " + h.typical_prior.toFixed(1) + " or less in recent years"],
  [h.sharp_name, "Sharpest rise since June", "up " + h.sharp_since.toFixed(1) + " points to " + h.sharp_now.toFixed(1) + "%, in " + h.sharp_state],
  [String(h.rising), "Regions still expected to rise", h.rising_name ? h.rising_name + " is the clear one" : "none stand out"],
  [h.cash_rate.toFixed(2) + "%", "Cash rate target", "the " + ordinal(h.hikes_2026) + " increase this year, in force from 4 November"]
].forEach(([value, label, note]) => {
  const article = document.createElement("article");
  article.className = "kpi";
  const lab = document.createElement("p");
  lab.className = "label";
  lab.textContent = label;
  const val = document.createElement("p");
  val.className = "value" + (value.length > 12 ? " compact" : "");
  val.textContent = value;
  const cap = document.createElement("p");
  cap.className = "note";
  cap.textContent = note;
  article.append(lab, val, cap);
  kpis.append(article);
});

document.getElementById("meaning").innerHTML = "<h3>What this means</h3>" + h.copy.meaning.map((paragraph) => `<p>${esc(paragraph)}</p>`).join("");
h.copy.actions.forEach((item, index) => {
  const article = document.createElement("article");
  article.className = "card action";
  const lab = document.createElement("p");
  lab.className = "label";
  lab.textContent = "Step " + (index + 1);
  const text = document.createElement("p");
  text.textContent = item;
  article.append(lab, text);
  document.getElementById("actions").append(article);
});

const tabs = [...document.querySelectorAll("nav.tabs button")];
function selectTab(button) {
  tabs.forEach((item) => {
    const on = item === button;
    item.setAttribute("aria-selected", on ? "true" : "false");
    item.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll("section.panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === button.getAttribute("aria-controls"));
  });
  refitCharts();
}
tabs.forEach((button, index) => {
  button.tabIndex = button.getAttribute("aria-selected") === "true" ? 0 : -1;
  button.addEventListener("click", () => selectTab(button));
  button.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(index + delta + tabs.length) % tabs.length];
    next.focus();
    selectTab(next);
  });
});
document.querySelectorAll("[data-tab]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const button = document.querySelector('nav.tabs button[aria-controls="' + link.dataset.tab + '"]');
    if (!button) return;
    selectTab(button);
    window.scrollTo(0, 0);
  });
});

const STATE_ORDER = ["New South Wales", "Victoria", "Queensland", "South Australia", "Western Australia", "Tasmania", "Northern Territory", "Australian Capital Territory"];
const stateNames = [...new Set(data.regions.map((row) => row.state))].sort((a, b) => {
  const ia = STATE_ORDER.indexOf(a);
  const ib = STATE_ORDER.indexOf(b);
  return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
});
document.querySelectorAll(".state-filter").forEach((sel) => {
  stateNames.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    sel.append(option);
  });
  sel.addEventListener("change", () => applyState(sel.value));
});

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function monthLabel(ym) {
  const parts = String(ym).split("-");
  return MONTHS[Number(parts[1]) - 1] + " " + parts[0];
}
function signed(value) {
  const number = Number(value);
  return (number > 0 ? "+" : "") + number.toFixed(1);
}
function ordinal(n) {
  const words = ["zero", "first", "second", "third", "fourth", "fifth", "sixth"];
  return words[n] || String(n);
}
function esc(value) {
  return String(value).replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}
function exactTable(caption, columns, rows) {
  const head = "<tr>" + columns.map((column) => `<th scope="col">${esc(column)}</th>`).join("") + "</tr>";
  const body = rows.map((row) => "<tr>" + row.map((cell) => `<td>${esc(cell)}</td>`).join("") + "</tr>").join("");
  return `<div class="table-scroll"><table><caption class="visually-hidden">${esc(caption)}</caption><thead>${head}</thead><tbody>${body}</tbody></table></div>`;
}
function jumpedRows() {
  if (!currentState) return data.already_chart;
  return data.regions
    .filter((row) => row.state === currentState)
    .slice()
    .sort((a, b) => b.since_june - a.since_june || a.name.localeCompare(b.name))
    .slice(0, 8);
}
function renderRows(query) {
  const needle = query.trim().toLowerCase();
  const list = data.regions.filter((row) => {
    if (currentState && row.state !== currentState) return false;
    return !needle || (row.name + " " + row.state).toLowerCase().includes(needle);
  });
  const body = document.getElementById("rows");
  if (!list.length) {
    body.innerHTML = '<tr><td colspan="4">No regions match.</td></tr>';
    return;
  }
  body.innerHTML = list.map((row) => `<tr>
    <td><strong>${esc(row.name)}</strong><br><span class="where">${esc(row.state)}</span></td>
    <td>${esc(row.rate.toFixed(1))}%</td>
    <td>${esc(signed(row.since_june))} points</td>
    <td><span class="pill ${esc(row.tone)}">${esc(row.outlook)}</span><br>${esc(signed(row.change))} points, ${esc(row.sure)}</td>
  </tr>`).join("");
}
function fillMapExact() {
  const list = data.regions.filter((row) => !currentState || row.state === currentState);
  document.getElementById("map-exact").innerHTML = exactTable(
    "Region rates and the outlook to December",
    ["Region", "State", "Now", "Since June", "By December"],
    list.map((row) => [row.name, row.state, row.rate.toFixed(1) + "%", signed(row.since_june) + " points", row.outlook])
  );
}
document.getElementById("national-exact").innerHTML = exactTable(
  "Official unemployment rate by month",
  ["Month", "Rate"],
  data.national_series.map((row) => [monthLabel(row.month), row.rate.toFixed(1) + "%"])
);
document.getElementById("states-exact").innerHTML = exactTable(
  "Official unemployment rate by state",
  ["State", "Sep 2025", "Sep 2026"],
  data.states.map((row) => [row.name, row.then.toFixed(1) + "%", row.now.toFixed(1) + "%"])
);
document.getElementById("find").addEventListener("input", (event) => renderRows(event.target.value));

const byCode = Object.fromEntries(data.regions.map((row) => [String(row.code), row]));
const regionMap = document.getElementById("map");
const regionSvg = regionMap.querySelector("svg");
const tip = document.getElementById("map-tip");
const homeBox = regionSvg.viewBox.baseVal;
const home = { x: homeBox.x, y: homeBox.y, w: homeBox.width, h: homeBox.height };
let view = { x: home.x, y: home.y, w: home.w, h: home.h };
let pinned = null;
let drag = null;

function applyView() {
  regionSvg.setAttribute("viewBox", view.x + " " + view.y + " " + view.w + " " + view.h);
}
function clampView(next) {
  const minW = home.w / 14;
  let w = Math.min(home.w, Math.max(minW, next.w));
  let h = home.h * (w / home.w);
  if (w >= home.w * 0.999) return { x: home.x, y: home.y, w: home.w, h: home.h };
  const marginX = w * 0.25;
  const marginY = h * 0.25;
  const x = Math.min(home.x + home.w - marginX, Math.max(home.x - w + marginX, next.x));
  const y = Math.min(home.y + home.h - marginY, Math.max(home.y - h + marginY, next.y));
  return { x: x, y: y, w: w, h: h };
}
function zoomBy(factor) {
  const cx = view.x + view.w / 2;
  const cy = view.y + view.h / 2;
  const w = view.w * factor;
  const h = view.h * factor;
  view = clampView({ x: cx - w / 2, y: cy - h / 2, w: w, h: h });
  applyView();
  hideTip();
}
document.getElementById("map-zoom-in").addEventListener("click", () => zoomBy(0.72));
document.getElementById("map-zoom-out").addEventListener("click", () => zoomBy(1 / 0.72));

function tipHtml(row) {
  return "<strong>" + esc(row.name) + "</strong><br>" +
    row.rate.toFixed(1) + "% now, " + signed(row.since_june) + " since June<br>" +
    esc(row.outlook) + " (" + esc(row.sure) + ")";
}
function showTip(path, event) {
  const row = byCode[path.getAttribute("data-code")];
  if (!row) return;
  tip.hidden = false;
  tip.innerHTML = tipHtml(row);
  const box = regionMap.getBoundingClientRect();
  let x = event.clientX - box.left + 14;
  let y = event.clientY - box.top + 14;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
  const tw = tip.offsetWidth;
  const th = tip.offsetHeight;
  if (x + tw > box.width - 8) tip.style.left = Math.max(8, event.clientX - box.left - tw - 14) + "px";
  if (y + th > box.height - 8) tip.style.top = Math.max(8, event.clientY - box.top - th - 14) + "px";
}
function hideTip() {
  tip.hidden = true;
  pinned = null;
}
function paintMap() {
  regionSvg.querySelectorAll("path[data-code]").forEach((path) => {
    const row = byCode[path.getAttribute("data-code")];
    path.classList.toggle("dim", Boolean(currentState) && (!row || row.state !== currentState));
  });
}
regionSvg.addEventListener("pointerover", (event) => {
  const path = event.target.closest && event.target.closest("path[data-code]");
  if (!path || pinned) return;
  showTip(path, event);
});
regionSvg.addEventListener("pointermove", (event) => {
  if (drag && event.pointerId === drag.id) {
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    drag.moved = true;
    const rect = regionSvg.getBoundingClientRect();
    view = clampView({
      x: drag.view.x - dx / rect.width * drag.view.w,
      y: drag.view.y - dy / rect.height * drag.view.h,
      w: drag.view.w,
      h: drag.view.h
    });
    applyView();
    hideTip();
    return;
  }
  if (pinned) return;
  const path = event.target.closest && event.target.closest("path[data-code]");
  if (path) showTip(path, event);
});
regionSvg.addEventListener("pointerout", (event) => {
  if (pinned || drag) return;
  const path = event.target.closest && event.target.closest("path[data-code]");
  const next = event.relatedTarget && event.relatedTarget.closest && event.relatedTarget.closest("path[data-code]");
  if (path && path !== next) hideTip();
});
regionSvg.addEventListener("pointerdown", (event) => {
  if (event.button !== undefined && event.button !== 0) return;
  drag = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    view: { x: view.x, y: view.y, w: view.w, h: view.h },
    moved: false,
    target: event.target.closest && event.target.closest("path[data-code]")
  };
  regionSvg.setPointerCapture(event.pointerId);
});
regionSvg.addEventListener("pointerup", (event) => {
  if (!drag || event.pointerId !== drag.id) return;
  const path = drag.target;
  const moved = drag.moved;
  const touch = event.pointerType === "touch";
  drag = null;
  if (moved || !touch) return;
  if (!path || pinned === path) hideTip();
  else { pinned = path; showTip(path, event); }
});
regionSvg.addEventListener("pointercancel", () => { drag = null; });
regionSvg.addEventListener("focusin", (event) => {
  const path = event.target.closest && event.target.closest("path[data-code]");
  if (!path) return;
  const rect = path.getBoundingClientRect();
  showTip(path, { clientX: rect.left + rect.width / 2, clientY: rect.top + 12 });
});
regionSvg.addEventListener("focusout", (event) => {
  const next = event.relatedTarget && event.relatedTarget.closest && event.relatedTarget.closest("path[data-code]");
  if (!next) hideTip();
});

function applyState(value) {
  currentState = value;
  document.querySelectorAll(".state-filter").forEach((sel) => {
    if (sel.value !== value) sel.value = value;
  });
  paintMap();
  renderRows(document.getElementById("find").value);
  fillMapExact();
  syncBars();
  syncStates();
  document.getElementById("filter-status").textContent = currentState ? "Showing " + currentState + "." : "Showing all states.";
}

const SHORT_STATE = {
  "New South Wales": "NSW",
  "Victoria": "Vic",
  "Queensland": "Qld",
  "South Australia": "SA",
  "Western Australia": "WA",
  "Tasmania": "Tas"
};
const BLUE = "#60a5fa";
const ORANGE = "#fb923c";
function stateFocus() {
  if (!currentState) return "";
  return data.states.some((row) => row.name === currentState) ? currentState : "";
}
function stateColors(kind) {
  const focus = stateFocus();
  return data.states.map((row) => {
    const on = !focus || row.name === focus;
    if (kind === "now") return on ? BLUE : "rgba(96,165,250,0.28)";
    return on ? ORANGE : "rgba(251,146,60,0.28)";
  });
}
function chartTheme() {
  Chart.defaults.font.family = 'ui-sans-serif, system-ui, "Segoe UI", sans-serif';
  Chart.defaults.color = "#a1a1aa";
  Chart.defaults.borderColor = "rgba(255,255,255,0.14)";
}
const dashedGrid = { color: "rgba(255,255,255,0.14)", borderDash: [4, 4], drawTicks: false };
const legendLabels = {
  color: "#d4d4d8",
  boxWidth: 10,
  boxHeight: 10,
  padding: 14,
  font: { size: 13 },
  useBorderRadius: true,
  borderRadius: 2
};
const tooltipTheme = {
  backgroundColor: "#111113",
  titleColor: "#f4f4f5",
  bodyColor: "#e4e4e7",
  borderColor: "#3a3a40",
  borderWidth: 1,
  padding: 10
};
function wrapLabel(label) {
  const words = String(label).split(" ");
  const lines = [];
  let line = "";
  words.forEach((word) => {
    const next = line ? line + " " + word : word;
    if (next.length > 22 && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  });
  if (line) lines.push(line);
  return lines.length > 1 ? lines : lines[0];
}
const labelLast = {
  id: "labelLast",
  afterDatasetsDraw(chart) {
    const points = chart.getDatasetMeta(0).data;
    if (!points.length) return;
    const last = points[points.length - 1];
    const value = chart.data.datasets[0].data.at(-1);
    if (!last || value === undefined) return;
    const ctx = chart.ctx;
    ctx.save();
    ctx.font = '600 13px ui-sans-serif, system-ui, "Segoe UI", sans-serif';
    ctx.fillStyle = "#f4f4f5";
    ctx.textAlign = "left";
    ctx.fillText(Number(value).toFixed(1) + "%", last.x + 8, last.y - 8);
    ctx.restore();
  }
};
function buildNational() {
  if (typeof Chart === "undefined" || Chart.getChart("national")) return;
  const labels = data.national_series.map((row) => monthLabel(row.month));
  new Chart(document.getElementById("national"), {
    type: "line",
    data: {
      labels: labels,
      datasets: [{
        label: "Official unemployment rate",
        data: data.national_series.map((row) => row.rate),
        borderColor: BLUE,
        backgroundColor: "rgba(96,165,250,0.16)",
        fill: true,
        tension: 0.25,
        pointRadius: (ctx) => ctx.dataIndex === ctx.dataset.data.length - 1 ? 4 : 0,
        pointHoverRadius: 4,
        pointBackgroundColor: BLUE,
        pointBorderColor: "#f4f4f5",
        borderWidth: 2.5
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 16, right: 52 } },
      plugins: {
        legend: { display: true, position: "top", align: "start", labels: legendLabels },
        tooltip: { ...tooltipTheme, callbacks: { label: (item) => Number(item.parsed.y).toFixed(1) + "%" } }
      },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { color: "#a1a1aa", maxTicksLimit: 6 } },
        y: {
          grid: dashedGrid,
          border: { display: false },
          ticks: { color: "#a1a1aa", callback: (value) => Number(value).toFixed(1) + "%" }
        }
      }
    },
    plugins: [labelLast]
  });
}
function barConfig(rows) {
  return {
    type: "bar",
    data: {
      labels: rows.map((row) => row.name),
      datasets: [{
        label: "Rise since June (points)",
        data: rows.map((row) => row.since_june),
        backgroundColor: BLUE,
        borderRadius: 3,
        maxBarThickness: 28
      }]
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "top", align: "start", labels: legendLabels },
        tooltip: { ...tooltipTheme, callbacks: { label: (item) => signed(item.parsed.x) + " points" } }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: dashedGrid,
          border: { display: false },
          ticks: { color: "#a1a1aa", callback: (value) => Number(value).toFixed(1) }
        },
        y: {
          grid: { display: false },
          border: { display: false },
          ticks: {
            color: "#d4d4d8",
            font: { size: 12 },
            autoSkip: false,
            callback(value) { return wrapLabel(this.getLabelForValue(value)); }
          }
        }
      }
    }
  };
}
function syncBars() {
  const rows = jumpedRows();
  document.getElementById("bars-exact").innerHTML = exactTable(
    "Regions with the largest rise since June",
    ["Region", "State", "Since June (points)"],
    rows.map((row) => [row.name, row.state, signed(row.since_june)])
  );
  document.getElementById("bar-insight").textContent = currentState
    ? "Points added to the unemployment rate from June to September 2026 in " + currentState + "."
    : h.copy.bar_insight;
  if (typeof Chart === "undefined") return;
  const canvas = document.getElementById("bars");
  const existing = Chart.getChart(canvas);
  const visible = document.getElementById("risk").classList.contains("active");
  if (!visible) {
    if (existing) existing.destroy();
    return;
  }
  if (existing) existing.destroy();
  new Chart(canvas, barConfig(rows));
}
function stateAxisMin() {
  const values = data.states.flatMap((row) => [row.then, row.now]);
  const low = Math.min(...values);
  return Math.max(0, Math.floor((low - 0.8) * 2) / 2);
}
function stateConfig() {
  return {
    type: "bar",
    data: {
      labels: data.states.map((row) => SHORT_STATE[row.name] || row.name),
      datasets: [
        { label: "Sep 2025", data: data.states.map((row) => row.then), backgroundColor: stateColors("then"), borderRadius: 3 },
        { label: "Sep 2026", data: data.states.map((row) => row.now), backgroundColor: stateColors("now"), borderRadius: 3 }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "top", align: "start", labels: legendLabels },
        tooltip: {
          ...tooltipTheme,
          callbacks: {
            title: (items) => data.states[items[0].dataIndex].name,
            label: (item) => item.dataset.label + ": " + Number(item.parsed.y).toFixed(1) + "%"
          }
        }
      },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { color: "#a1a1aa", maxRotation: 0 } },
        y: {
          min: stateAxisMin(),
          grid: dashedGrid,
          border: { display: false },
          ticks: { color: "#a1a1aa", callback: (value) => Number(value).toFixed(1) + "%" }
        }
      }
    }
  };
}
function syncStates() {
  if (typeof Chart === "undefined") return;
  const canvas = document.getElementById("states");
  const existing = Chart.getChart(canvas);
  if (existing) {
    existing.data.datasets[0].backgroundColor = stateColors("then");
    existing.data.datasets[1].backgroundColor = stateColors("now");
    existing.update();
    return;
  }
  if (!document.getElementById("risk").classList.contains("active")) return;
  new Chart(canvas, stateConfig());
}
function refitCharts() {
  // A chart drawn while its tab is hidden is measured as 0. Draw it once the tab is on screen, then resize.
  requestAnimationFrame(() => {
    if (document.getElementById("overview").classList.contains("active")) buildNational();
    if (document.getElementById("risk").classList.contains("active")) {
      syncBars();
      syncStates();
    }
    if (typeof Chart === "undefined") return;
    document.querySelectorAll("canvas").forEach((canvas) => {
      const chart = Chart.getChart(canvas);
      if (chart) chart.resize();
    });
  });
}

fillMapExact();
renderRows("");
syncBars();
if (typeof Chart !== "undefined") {
  chartTheme();
  buildNational();
  refitCharts();
}
</script>
</body>
</html>
"""
