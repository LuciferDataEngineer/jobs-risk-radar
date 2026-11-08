"""Track the walk-forward result in a local MLflow file store."""

from __future__ import annotations

import mlflow

from jrr.forecast import MODEL_COLUMNS, run_forecast
from jrr.paths import root


def train_and_track(frame=None) -> dict:
    result = run_forecast(frame)
    tracking = root() / "mlruns"
    tracking.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking.as_uri())
    mlflow.set_experiment("sa4-next-quarter")
    metrics = {
        key: value
        for key, value in result["summary"]["backtest"].items()
        if isinstance(value, float)
    }
    with mlflow.start_run(run_name="walk-forward-next-quarter"):
        mlflow.log_params(
            {
                "n_features": len(MODEL_COLUMNS),
                "material_rise_points": 0.3,
                "train_rows": result["summary"]["train_rows"],
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(result["regressor"], artifact_path="regressor")
    return result
