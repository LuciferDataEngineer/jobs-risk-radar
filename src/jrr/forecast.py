"""Next-quarter unemployment forecasts and a walk-forward check against two simple rules."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import polars as pl
from lightgbm import LGBMClassifier, LGBMRegressor
from scipy.stats import spearmanr

from jrr.columns import FEATURE_COLUMNS, MATERIAL_RISE
from jrr.features import build_feature_frame, latest_cash_override
from jrr.paths import report_dir

MODEL_COLUMNS = [*FEATURE_COLUMNS, "month_num", "state_code_num"]
EXCESS_FLAG = 0.2


def _regressor() -> LGBMRegressor:
    return LGBMRegressor(
        n_estimators=120,
        learning_rate=0.06,
        num_leaves=16,
        min_child_samples=30,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=7,
        verbosity=-1,
    )


def _classifier() -> LGBMClassifier:
    return LGBMClassifier(
        n_estimators=120,
        learning_rate=0.06,
        num_leaves=16,
        min_child_samples=30,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=7,
        verbosity=-1,
    )


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["month"] = pd.to_datetime(data["month"], utc=True).dt.tz_localize(None)
    data["origin"] = data["month"].dt.to_period("M").dt.to_timestamp()
    return data


def _fit_predict(
    train: pd.DataFrame, test: pd.DataFrame, return_models: bool = False
) -> tuple:
    regressor = _regressor()
    classifier = _classifier()
    regressor.fit(train[MODEL_COLUMNS], train["target_delta"])
    labels = (train["target_delta"] >= MATERIAL_RISE).astype(int)
    # A constant label would make the classifier meaningless; fall back to the base rate.
    if labels.nunique() < 2:
        probability = np.full(len(test), float(labels.mean()))
    else:
        classifier.fit(train[MODEL_COLUMNS], labels)
        probability = classifier.predict_proba(test[MODEL_COLUMNS])[:, 1]
    predicted = regressor.predict(test[MODEL_COLUMNS])
    if return_models:
        return predicted, probability, regressor, classifier
    return predicted, probability


def walk_forward(frame: pd.DataFrame) -> dict:
    data = _prepare(frame)
    labeled = data.dropna(subset=["target_delta", "usual_next_quarter_change", "delta_3"])
    origins = (
        labeled.loc[
            (labeled["origin"] >= "2020-03-01") & (labeled["origin"] <= "2026-06-01"),
            "origin",
        ]
        .drop_duplicates()
        .sort_values()
    )
    origins = [origin for origin in origins if origin.month in (3, 6, 9, 12)]
    rows = []
    for origin in origins:
        train = labeled[labeled["origin"] <= origin - pd.DateOffset(months=3)]
        test = labeled[labeled["origin"] == origin]
        if len(train) < 500 or test.empty:
            continue
        predicted, probability = _fit_predict(train, test)
        piece = test[
            ["sa4_code", "origin", "target_delta", "usual_next_quarter_change", "delta_3"]
        ].copy()
        piece["predicted"] = predicted
        piece["probability"] = probability
        rows.append(piece)
    predictions = pd.concat(rows, ignore_index=True)
    metrics = _metrics(predictions)
    return {"metrics": metrics, "predictions": predictions}


def _metrics(predictions: pd.DataFrame) -> dict:
    actual = predictions["target_delta"].to_numpy()
    model_error = np.abs(actual - predictions["predicted"].to_numpy())
    seasonal_error = np.abs(actual - predictions["usual_next_quarter_change"].to_numpy())
    momentum_error = np.abs(actual - predictions["delta_3"].to_numpy())
    spears = []
    hits = []
    for _, group in predictions.groupby("origin"):
        if group["target_delta"].nunique() < 2 or group["predicted"].nunique() < 2:
            continue
        coef = spearmanr(group["predicted"], group["target_delta"]).statistic
        if np.isfinite(coef):
            spears.append(float(coef))
        k = min(10, len(group))
        pred_top = set(group.nlargest(k, "predicted")["sa4_code"])
        actual_top = set(group.nlargest(k, "target_delta")["sa4_code"])
        hits.append(len(pred_top & actual_top) / k)
    material = (predictions["target_delta"] >= MATERIAL_RISE).astype(int)
    called = (predictions["probability"] >= 0.5).astype(int)
    accuracy = float((called == material).mean())
    majority = float(max(material.mean(), 1 - material.mean()))
    return {
        "origins": int(predictions["origin"].nunique()),
        "rows": int(len(predictions)),
        "mae_model": float(model_error.mean()),
        "mae_usual_pace": float(seasonal_error.mean()),
        "mae_last_quarter_repeated": float(momentum_error.mean()),
        "mean_rank_agreement": float(np.mean(spears)) if spears else None,
        "top10_hit_rate": float(np.mean(hits)) if hits else None,
        "material_rise_share": float(material.mean()),
        "call_accuracy": accuracy,
        "majority_accuracy": majority,
    }


def fit_latest(frame: pd.DataFrame) -> dict:
    """Train on every quarter that has already happened, then score the latest month."""
    data = _prepare(frame)
    labeled = data.dropna(subset=["target_delta", "usual_next_quarter_change"])
    latest_month = data["origin"].max()
    train = labeled[labeled["origin"] <= latest_month - pd.DateOffset(months=3)]
    live = data[data["origin"] == latest_month].copy()
    cash = latest_cash_override()
    live["cash_rate"] = cash["cash_rate"]
    live["cash_delta_3"] = cash["cash_delta_3"]
    predicted, probability, regressor, classifier = _fit_predict(train, live, return_models=True)
    live["predicted_change"] = predicted
    live["rise_chance"] = probability
    live["usual_change"] = live["usual_next_quarter_change"]
    live["excess"] = live["predicted_change"] - live["usual_change"]
    payload = live[
        [
            "sa4_code",
            "sa4_name",
            "state_code",
            "state_name",
            "origin",
            "unemp_rate",
            "labour_force",
            "delta_3",
            "predicted_change",
            "usual_change",
            "excess",
            "rise_chance",
            "participation_rate",
            "youth_unemp_rate",
        ]
    ].copy()
    return {
        "scores": payload,
        "train_rows": int(len(train)),
        "cash_adjustment": cash,
        "regressor": regressor,
        "classifier": classifier,
    }


def smoke_score() -> dict:
    """Container entry: train from the snapshot and print a one-line result."""
    frame = build_feature_frame().to_pandas()
    result = fit_latest(frame)
    scores = result["scores"]
    flagged = int(((scores["excess"] >= EXCESS_FLAG) & (scores["predicted_change"] > 0)).sum())
    top = scores.sort_values("excess", ascending=False).iloc[0]
    return {
        "regions": int(len(scores)),
        "flagged": flagged,
        "top": str(top["sa4_name"]),
        "change": float(top["predicted_change"]),
    }


def run_forecast(frame: pd.DataFrame | None = None) -> dict:
    if frame is None:
        frame = build_feature_frame().to_pandas()
    elif isinstance(frame, pl.DataFrame):
        frame = frame.to_pandas()
    checked = walk_forward(frame)
    latest = fit_latest(frame)
    report_dir().mkdir(parents=True, exist_ok=True)
    checked["predictions"].to_parquet(report_dir() / "backtest_predictions.parquet", index=False)
    latest["scores"].to_parquet(report_dir() / "live_scores.parquet", index=False)
    summary = {
        "backtest": checked["metrics"],
        "train_rows": latest["train_rows"],
        "cash_adjustment": latest["cash_adjustment"],
        "scored_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    (report_dir() / "backtest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return {
        "summary": summary,
        "scores": latest["scores"],
        "predictions": checked["predictions"],
        "regressor": latest["regressor"],
        "classifier": latest["classifier"],
    }
