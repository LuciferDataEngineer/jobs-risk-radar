"""Dagster asset graph for the radar.

``make pipeline`` runs each stage once. Materialising this graph runs the same
functions, with outputs passed between assets.
"""

from dagster import Definitions, asset

from jrr.dashboard import build_site
from jrr.drift import build_drift
from jrr.features import build_feature_frame, retrieve_historical
from jrr.model import train_and_track
from jrr.quality import run_quality
from jrr.warehouse import run_dbt


@asset
def checked_snapshot() -> dict:
    return run_quality()


@asset(deps=[checked_snapshot])
def warehouse() -> None:
    run_dbt()


@asset(deps=[checked_snapshot])
def historical_features():
    return retrieve_historical(build_feature_frame())


@asset
def scored_regions(historical_features):
    tracked = train_and_track(historical_features)
    tracked.pop("regressor", None)
    tracked.pop("classifier", None)
    return tracked


@asset
def drift_report(historical_features, scored_regions) -> dict:
    return build_drift(historical_features, scored_regions["predictions"])


@asset(deps=[warehouse])
def stakeholder_site(scored_regions, drift_report) -> dict:
    return build_site(scored_regions["scores"], scored_regions["summary"])


defs = Definitions(
    assets=[
        checked_snapshot,
        warehouse,
        historical_features,
        scored_regions,
        drift_report,
        stakeholder_site,
    ]
)
