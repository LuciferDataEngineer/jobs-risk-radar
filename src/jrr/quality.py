"""Checks on the committed snapshot. Failures stop the pipeline."""

from __future__ import annotations

import json

import polars as pl

from jrr.paths import report_dir, snapshot_dir


def run_quality() -> dict:
    sa4 = pl.read_parquet(snapshot_dir() / "sa4_month.parquet")
    states = pl.read_parquet(snapshot_dir() / "state_unemployment.parquet")
    cash = pl.read_parquet(snapshot_dir() / "cash_rate_month.parquet")
    approvals = pl.read_parquet(snapshot_dir() / "approvals.parquet")
    vacancies = pl.read_parquet(snapshot_dir() / "vacancies.parquet")
    checks: list[tuple[str, bool]] = []

    checks.append(("one row per region-month", sa4.select(["sa4_code", "month"]).n_unique() == sa4.height))
    checks.append(("87 regions", sa4["sa4_code"].n_unique() == 87))
    checks.append(("rates in a plausible range", bool(sa4["unemp_rate"].is_between(0, 40).all())))
    checks.append(("no missing unemployment rates", sa4["unemp_rate"].null_count() == 0))
    september = sa4.filter(pl.col("month") == pl.datetime(2026, 9, 1))
    employed = float(september["employed"].sum())
    checks.append(("September 2026 employment matches the ABS total", abs(employed - 14743.820256863) < 0.01))
    national = states.filter(
        (pl.col("region_code") == "AUS") & (pl.col("month") == pl.date(2026, 9, 1))
    )
    national_rate = float(national["unemp_rate_sa"][0])
    checks.append(("September 2026 national rate is 4.7 percent", abs(national_rate - 4.71834873) < 1e-4))
    november = cash.filter(pl.col("month") == pl.datetime(2026, 11, 1))
    checks.append(("November 2026 cash rate target is 4.85", float(november["cash_rate_target"][0]) == 4.85))
    aus_approvals = approvals.filter(
        (pl.col("region_code") == "AUS") & (pl.col("month") == pl.date(2026, 9, 1))
    )
    checks.append(("September 2026 dwelling approvals are populated", float(aus_approvals["dwelling_approvals"][0]) == 18318))
    checks.append(("vacancies cover the states and Australia", vacancies["region_code"].n_unique() == 9))

    failed = [name for name, ok in checks if not ok]
    report = {
        "checks": [{"name": name, "passed": ok} for name, ok in checks],
        "sa4_rows": sa4.height,
        "regions": sa4["sa4_code"].n_unique(),
        "september_2026_employed_thousands": employed,
        "september_2026_national_unemployment_rate": national_rate,
        "september_2026_region_rate_min": float(september["unemp_rate"].min()),
        "september_2026_region_rate_median": float(september["unemp_rate"].median()),
        "september_2026_region_rate_max": float(september["unemp_rate"].max()),
    }
    report_dir().mkdir(parents=True, exist_ok=True)
    (report_dir() / "quality.json").write_text(json.dumps(report, indent=2) + "\n")
    if failed:
        raise RuntimeError("Data quality failed: " + "; ".join(failed))
    return report
