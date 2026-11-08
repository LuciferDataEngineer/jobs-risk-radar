"""Repository paths. JRR_ROOT overrides the checkout root in CI and containers."""

from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    override = os.environ.get("JRR_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


def snapshot_dir() -> Path:
    return root() / "data" / "snapshot"


def boundary_path() -> Path:
    return root() / "data" / "boundaries" / "sa4.geojson"


def feature_dir() -> Path:
    return root() / "data" / "features"


def feast_dir() -> Path:
    return root() / "data" / "feast"


def warehouse_path() -> Path:
    override = os.environ.get("JRR_DUCKDB")
    if override:
        return Path(override)
    return root() / "data" / "warehouse" / "jrr.duckdb"


def report_dir() -> Path:
    return root() / "reports"


def site_dir() -> Path:
    return root() / "site"


def dbt_dir() -> Path:
    return root() / "dbt_project"


def feast_repo_dir() -> Path:
    return root() / "feast_repo"
