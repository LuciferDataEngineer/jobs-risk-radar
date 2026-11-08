"""Stakeholder pages. Plain language only; the technical record lives in the README."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import polars as pl

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
    generated = datetime.now(MELBOURNE).strftime("%A %-d %B %Y, %-I:%M %p %Z")
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


def _page(payload: dict) -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    return PAGE.replace("/*__DATA__*/null", data)


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Jobs Risk Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,680&family=Source+Sans+3:wght@400;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {
  --ink: #1c1915;
  --muted: #5c564c;
  --paper: #f4f0e6;
  --card: #fffdf8;
  --line: #e3d9c6;
  --teal: #0e6b62;
  --teal-dark: #0a4f49;
  --high: #9f1239;
  --watch: #c2410c;
  --steady: #8a8175;
  --easier: #0f766e;
  --shadow: 0 10px 30px rgba(48, 36, 18, 0.06);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(1200px 400px at 90% -10%, #efe2c4 0%, transparent 55%),
    var(--paper);
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 18px;
  line-height: 1.45;
}
header.banner {
  padding: 28px 7vw 8px;
}
.kicker {
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-size: 12px;
  font-weight: 700;
  color: var(--teal-dark);
  margin: 0 0 8px;
}
h1 {
  font-family: Fraunces, Georgia, serif;
  font-weight: 680;
  font-size: clamp(36px, 5vw, 58px);
  line-height: 1.02;
  margin: 0 0 10px;
}
.lede { max-width: 760px; font-size: 20px; margin: 0; }
.when { color: var(--muted); font-size: 15px; margin-top: 8px; }
nav.tabs {
  display: flex;
  gap: 8px;
  padding: 18px 7vw 0;
  overflow-x: auto;
}
nav.tabs button {
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-weight: 700;
  padding: 10px 16px;
  border-radius: 999px;
  cursor: pointer;
}
nav.tabs button[aria-selected="true"] {
  background: var(--ink);
  color: #f7f1e4;
}
main { padding: 18px 7vw 48px; }
section.panel { display: none; }
section.panel.active { display: block; }
.kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
  margin: 8px 0 18px;
}
.kpi {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 14px 16px 12px;
  box-shadow: var(--shadow);
  min-height: 132px;
}
.kpi .value {
  font-family: Fraunces, Georgia, serif;
  font-size: 32px;
  line-height: 1.05;
  margin: 4px 0;
}
.kpi .label { font-size: 14px; font-weight: 700; color: var(--muted); }
.kpi .note { font-size: 15px; }
.kpi.high { border-top: 5px solid var(--high); }
.kpi.watch { border-top: 5px solid var(--watch); }
.kpi.steady { border-top: 5px solid var(--teal); }
.layout { display: grid; grid-template-columns: 1.4fr 0.8fr; gap: 16px; }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 16px 16px 12px;
  box-shadow: var(--shadow);
}
.card h2 {
  font-family: Fraunces, Georgia, serif;
  font-size: 26px;
  margin: 0 0 4px;
}
.card p.insight { margin: 0 0 10px; color: var(--muted); }
#map { height: 540px; border-radius: 14px; }
.legend { display: flex; flex-wrap: wrap; gap: 10px 16px; font-size: 14px; margin-top: 8px; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; }
.meaning {
  background: #12312e;
  color: #f6f1e6;
  border-radius: 18px;
  padding: 18px 18px 8px;
}
.meaning h2 { font-family: Fraunces, Georgia, serif; margin: 0 0 8px; }
.actions li { margin: 8px 0; }
table { width: 100%; border-collapse: collapse; font-size: 16px; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); }
.pill { font-weight: 700; }
.pill.high { color: var(--high); }
.pill.watch { color: var(--watch); }
.pill.steady { color: var(--steady); }
.pill.easier { color: var(--easier); }
input[type="search"] {
  width: min(360px, 100%);
  font: inherit;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  margin: 8px 0 12px;
  background: #fff;
}
footer.sources {
  margin-top: 22px;
  color: var(--muted);
  font-size: 14px;
}
footer.sources a { color: var(--teal-dark); }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  #map { height: 420px; }
  body { font-size: 17px; }
}
</style>
</head>
<body>
<header class="banner">
  <p class="kicker">Australia · next three months</p>
  <h1 id="title">Jobs Risk Radar</h1>
  <p class="lede" id="lede"></p>
  <p class="when" id="when"></p>
</header>
<nav class="tabs" role="tablist">
  <button role="tab" id="tab-overview" aria-controls="overview" aria-selected="true">Overview</button>
  <button role="tab" id="tab-map" aria-controls="map-panel" aria-selected="false">Regions map</button>
  <button role="tab" id="tab-risk" aria-controls="risk" aria-selected="false">Who's at risk</button>
  <button role="tab" id="tab-do" aria-controls="do" aria-selected="false">What to do</button>
</nav>
<main>
  <section id="overview" class="panel active" role="tabpanel">
    <div class="kpis" id="kpis"></div>
    <div class="layout">
      <article class="card">
        <h2>Unemployment has already climbed</h2>
        <p class="insight" id="line-insight"></p>
        <canvas id="national" height="140"></canvas>
      </article>
      <article class="meaning" id="meaning"></article>
    </div>
  </section>
  <section id="map-panel" class="panel" role="tabpanel">
    <article class="card">
      <h2>Where the rate is expected to rise, hold or ease by December</h2>
      <p class="insight">Colour shows the outlook from September to December. Hover a region for the rate today and what the next three months look like.</p>
      <div id="map"></div>
      <div class="legend">
        <span><i class="swatch" style="background:#9f1239"></i>Likely to rise</span>
        <span><i class="swatch" style="background:#c2410c"></i>Little relief, or less than last year</span>
        <span><i class="swatch" style="background:#d6d3c4"></i>Should ease</span>
        <span><i class="swatch" style="background:#0f766e"></i>A clearer easing</span>
      </div>
      <p class="insight">Western Australia's two remote outback regions are drawn together, matching the published figures. Borders are simplified.</p>
    </article>
  </section>
  <section id="risk" class="panel" role="tabpanel">
    <div class="layout">
      <article class="card">
        <h2 id="bar-title">Where the jobless rate has already jumped</h2>
        <p class="insight" id="bar-insight"></p>
        <canvas id="bars" height="220"></canvas>
      </article>
      <article class="card">
        <h2>The states, one year apart</h2>
        <p class="insight" id="state-insight"></p>
        <canvas id="states" height="220"></canvas>
      </article>
    </div>
    <article class="card" style="margin-top:16px">
      <h2>Every region</h2>
      <input id="find" type="search" placeholder="Find a region or state" aria-label="Find a region">
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr><th>Region</th><th>Now</th><th>Since June</th><th>By December</th></tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
    </article>
  </section>
  <section id="do" class="panel" role="tabpanel">
    <article class="card">
      <h2>What to do before Christmas</h2>
      <ul class="actions" id="actions"></ul>
    </article>
  </section>
  <footer class="sources">
    <p>Sources: Australian Bureau of Statistics, Regional Labour Force, September 2026 (modelled regional rates) and Labour Force, Australia, September 2026 (official state and national rates); ABS Job Vacancies and Building Approvals; Reserve Bank of Australia cash rate target. Region boundaries from the ABS, simplified for this map. All ABS material is free to reuse with credit (CC BY 4.0). Prepared <span id="stamp"></span>. This is an independent briefing, not a government site. Rates are rounded to one decimal place.</p>
  </footer>
</main>
<script id="radar" type="application/json">/*__DATA__*/null</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const data = JSON.parse(document.getElementById("radar").textContent);
const h = data.headlines;
const toneColor = { high: "#9f1239", watch: "#c2410c", steady: "#d6d3c4", easier: "#0f766e" };

document.getElementById("lede").textContent = h.copy.lede;
document.getElementById("when").textContent = "Regional figures are for September 2026, the latest release. The outlook runs to December 2026. The cash rate target of " + h.cash_rate.toFixed(2) + "% is the rate in force now. A point means a percentage point of the unemployment rate. Updated " + h.generated + ".";
document.getElementById("stamp").textContent = h.generated;
document.getElementById("line-insight").textContent = h.copy.line_insight;
document.getElementById("state-insight").textContent = h.copy.state_insight;
document.getElementById("bar-insight").textContent = h.copy.bar_insight;

const kpis = [
  ["watch", h.national_rate.toFixed(1) + "%", "Unemployment in Australia", "up from " + h.national_year_ago.toFixed(1) + "% a year ago"],
  ["high", "+" + h.typical_since_june.toFixed(1), "Typical rise since June", "points, versus about " + h.typical_prior.toFixed(1) + " or less in recent years"],
  ["high", h.sharp_name, "Sharpest rise since June", "up " + h.sharp_since.toFixed(1) + " points to " + h.sharp_now.toFixed(1) + "%, in " + h.sharp_state],
  ["watch", String(h.rising), "Regions still expected to rise", h.rising_name ? h.rising_name + " is the clear one" : "none stand out"],
  ["steady", h.cash_rate.toFixed(2) + "%", "Cash rate target", "the " + ordinal(h.hikes_2026) + " increase this year, in force from 4 November"]
];
document.getElementById("kpis").innerHTML = kpis.map(([tone, value, label, note]) =>
  `<article class="kpi ${tone}"><div class="label">${label}</div><div class="value">${value}</div><div class="note">${note}</div></article>`
).join("");
document.getElementById("meaning").innerHTML = "<h2>What this means</h2>" + h.copy.meaning.map((paragraph) => `<p>${paragraph}</p>`).join("");

const tabs = document.querySelectorAll("nav.tabs button");
tabs.forEach((button) => button.addEventListener("click", () => {
  tabs.forEach((item) => item.setAttribute("aria-selected", item === button ? "true" : "false"));
  document.querySelectorAll("section.panel").forEach((panel) => panel.classList.remove("active"));
  document.getElementById(button.getAttribute("aria-controls")).classList.add("active");
  if (button.id === "tab-map") map.invalidateSize();
}));

Chart.register(ChartDataLabels);
Chart.defaults.font.family = '"Source Sans 3", sans-serif';
Chart.defaults.color = "#1c1915";
const labelLast = {
  id: "labelLast",
  afterDatasetsDraw(chart) {
    const points = chart.getDatasetMeta(0).data;
    const last = points[points.length - 1];
    const value = chart.data.datasets[0].data.at(-1);
    const ctx = chart.ctx;
    ctx.save();
    ctx.font = "700 14px Source Sans 3";
    ctx.fillStyle = "#0e6b62";
    ctx.fillText(value.toFixed(1) + "%", last.x - 36, last.y - 10);
    ctx.restore();
  }
};
new Chart(document.getElementById("national"), {
  type: "line",
  data: {
    labels: data.national_series.map((d) => d.month),
    datasets: [{
      data: data.national_series.map((d) => d.rate),
      borderColor: "#0e6b62",
      backgroundColor: "rgba(14,107,98,0.12)",
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      pointHoverRadius: 4,
      borderWidth: 2.5
    }]
  },
  options: {
    plugins: { legend: { display: false }, datalabels: { display: false }, tooltip: { callbacks: { label: (c) => c.parsed.y.toFixed(1) + "%" } } },
    scales: { x: { ticks: { maxTicksLimit: 6 } }, y: { ticks: { callback: (v) => v.toFixed(1) + "%" } } }
  },
  plugins: [labelLast]
});
new Chart(document.getElementById("bars"), {
  type: "bar",
  data: {
    labels: data.already_chart.map((d) => d.name),
    datasets: [{ data: data.already_chart.map((d) => d.since_june), backgroundColor: "#c2410c", borderRadius: 6 }]
  },
  options: {
    indexAxis: "y",
    plugins: { legend: { display: false }, datalabels: { anchor: "end", align: "end", formatter: (v) => (v > 0 ? "+" : "") + v.toFixed(1) } },
    scales: { x: { ticks: { callback: (v) => v.toFixed(1) } } },
    layout: { padding: { right: 36 } }
  }
});
new Chart(document.getElementById("states"), {
  type: "bar",
  data: {
    labels: data.states.map((d) => d.name.replace("New South Wales", "NSW").replace("South Australia", "SA").replace("Western Australia", "WA")),
    datasets: [
      { label: "Sep 2025", data: data.states.map((d) => d.then), backgroundColor: "#e7d7b8" },
      { label: "Sep 2026", data: data.states.map((d) => d.now), backgroundColor: "#0e6b62" }
    ]
  },
  options: {
    plugins: { datalabels: { display: false } },
    scales: { y: { ticks: { callback: (v) => v.toFixed(1) + "%" } } }
  }
});

function renderRows(query) {
  const needle = query.trim().toLowerCase();
  const list = data.regions.filter((row) => !needle || (row.name + " " + row.state).toLowerCase().includes(needle));
  document.getElementById("rows").innerHTML = list.map((row) => `<tr>
    <td><strong>${row.name}</strong><br><span style="color:#5c564c">${row.state}</span></td>
    <td>${row.rate.toFixed(1)}%</td>
    <td>${signed(row.since_june)} points</td>
    <td><span class="pill ${row.tone}">${row.outlook}</span><br>${signed(row.change)} points, ${row.sure}</td>
  </tr>`).join("");
}
document.getElementById("find").addEventListener("input", (event) => renderRows(event.target.value));
renderRows("");

document.getElementById("actions").innerHTML = h.copy.actions.map((item) => `<li>${item}</li>`).join("");

function signed(value) {
  return (value > 0 ? "+" : "") + value.toFixed(1);
}
function ordinal(n) {
  const words = ["zero", "first", "second", "third", "fourth", "fifth", "sixth"];
  return words[n] || String(n);
}

const map = L.map("map", { scrollWheelZoom: false });
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap &copy; CARTO",
  subdomains: "abcd",
  maxZoom: 12
}).addTo(map);
const byCode = Object.fromEntries(data.regions.map((row) => [row.code, row]));
fetch("sa4.geojson").then((response) => response.json()).then((geo) => {
  const layer = L.geoJSON(geo, {
    style: (feature) => {
      const row = byCode[feature.properties.radar_code];
      return {
        color: "#ffffff",
        weight: 0.6,
        fillColor: row ? toneColor[row.tone] : "#eee",
        fillOpacity: 0.88
      };
    },
    onEachFeature: (feature, layer) => {
      const row = byCode[feature.properties.radar_code];
      if (!row) return;
      layer.bindTooltip(`<strong>${row.name}</strong><br>${row.rate.toFixed(1)}% now, ${signed(row.since_june)} since June<br>${row.outlook} (${row.sure})`);
    }
  }).addTo(map);
  map.fitBounds(layer.getBounds(), { padding: [12, 12] });
});
</script>
</body>
</html>
"""
