"""Data and prediction drift between earlier scored quarters and the recent ones."""

from __future__ import annotations

import json

import pandas as pd
from evidently.metric_preset import DataDriftPreset
from evidently.report import Report

from jrr.columns import FEATURE_COLUMNS
from jrr.paths import report_dir, site_dir


def build_drift(features: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    frame = features.copy()
    frame["month"] = pd.to_datetime(frame["month"], utc=True).dt.tz_localize(None)
    preds = predictions.rename(columns={"predicted": "predicted_change"})
    preds["origin"] = pd.to_datetime(preds["origin"])
    merged = frame.merge(
        preds[["sa4_code", "origin", "predicted_change"]],
        left_on=["sa4_code", "month"],
        right_on=["sa4_code", "origin"],
        how="inner",
    )
    columns = [*FEATURE_COLUMNS, "predicted_change"]
    reference = merged[merged["month"].dt.year.between(2020, 2022)][columns].dropna()
    current = merged[merged["month"].dt.year.between(2024, 2026)][columns].dropna()
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)
    destination = site_dir() / "drift" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    report.save_html(str(destination))
    payload = report.as_dict()
    drifted = _count_drifted(payload)
    summary = {
        "reference_rows": int(len(reference)),
        "current_rows": int(len(current)),
        "reference_years": "2020-2022",
        "current_years": "2024-2026",
        "columns": len(columns),
        "drifted_columns": drifted,
        "report": "site/drift/index.html",
    }
    report_dir().mkdir(parents=True, exist_ok=True)
    (report_dir() / "drift_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _count_drifted(payload: dict) -> int | None:
    count = 0
    found = False

    def walk(node: object) -> None:
        nonlocal count, found
        if isinstance(node, dict):
            if node.get("drift_detected") is True:
                count += 1
                found = True
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return count if found else None
