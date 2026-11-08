"""Point-in-time features for each labour-market region.

The offline feature table is parquet. Feast's local DuckDB offline store
retrieves it as of an entity timestamp, so a later unemployment rate cannot
leak into an earlier decision. The SQLite online store holds the latest row
for a live lookup.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd
import polars as pl

from jrr.columns import FEATURE_COLUMNS
from jrr.paths import feast_dir, feature_dir, snapshot_dir

TIMESTAMP = "event_timestamp"
ENTITY = "sa4_code"


def _month(column: str = "month") -> pl.Expr:
    return pl.col(column).cast(pl.Date).dt.truncate("1mo")


def build_feature_frame() -> pl.DataFrame:
    """Features known at each region-month, plus the realised change three months later."""
    labour = pl.read_parquet(snapshot_dir() / "sa4_month.parquet").with_columns(
        _month().alias("month")
    )
    labour = labour.sort(["sa4_code", "month"]).with_columns(
        pl.col("unemp_rate").shift(3).over(ENTITY).alias("unemp_rate_lag3"),
        pl.col("unemp_rate").shift(9).over(ENTITY).alias("unemp_rate_lag9"),
        pl.col("unemp_rate").shift(12).over(ENTITY).alias("unemp_rate_lag12"),
        pl.col("participation_rate").shift(3).over(ENTITY).alias("participation_lag3"),
        pl.col("youth_unemp_rate").shift(3).over(ENTITY).alias("youth_lag3"),
        pl.col("employed").shift(3).over(ENTITY).alias("employed_lag3"),
    )
    labour = labour.with_columns(
        (pl.col("unemp_rate") - pl.col("unemp_rate_lag3")).alias("delta_3"),
        (pl.col("unemp_rate") - pl.col("unemp_rate_lag12")).alias("delta_12"),
        (pl.col("unemp_rate_lag9") - pl.col("unemp_rate_lag12")).alias(
            "usual_next_quarter_change"
        ),
        (pl.col("participation_rate") - pl.col("participation_lag3")).alias(
            "participation_delta_3"
        ),
        (pl.col("youth_unemp_rate") - pl.col("youth_lag3")).alias("youth_delta_3"),
        (
            (pl.col("employed") - pl.col("employed_lag3")) / pl.col("employed_lag3")
        ).alias("employment_growth_3"),
        pl.col("month").dt.month().alias("month_num"),
        pl.col("state_code").cast(pl.Int32).alias("state_code_num"),
    )

    vacancies = _vacancy_features()
    approvals = _approval_features()
    cash = _cash_features()
    state_rates = _state_rate_features()

    frame = (
        labour.join(vacancies, on=["state_code", "month"], how="left")
        .join(approvals, on=["state_code", "month"], how="left")
        .join(cash, on="month", how="left")
        .join(state_rates, on=["state_code", "month"], how="left")
    )
    future = labour.select(
        ENTITY,
        pl.col("month").alias("future_month"),
        pl.col("unemp_rate").alias("future_rate"),
    )
    frame = frame.with_columns(pl.col("month").dt.offset_by("3mo").alias("future_month"))
    frame = frame.join(future, on=[ENTITY, "future_month"], how="left").with_columns(
        (pl.col("future_rate") - pl.col("unemp_rate")).alias("target_delta"),
        pl.col("month").cast(pl.Datetime("us")).dt.replace_time_zone("UTC").alias(TIMESTAMP),
    )
    keep = [
        ENTITY,
        "sa4_name",
        "state_code",
        "state_name",
        "month",
        TIMESTAMP,
        "month_num",
        "state_code_num",
        "labour_force",
        "employed",
        "unemployed",
        *FEATURE_COLUMNS,
        "target_delta",
    ]
    return frame.select(keep).sort([ENTITY, "month"])


def _vacancy_features() -> pl.DataFrame:
    frame = pl.read_parquet(snapshot_dir() / "vacancies.parquet")
    frame = frame.filter(pl.col("region_code") != "AUS").sort(["region_code", "quarter_end"])
    frame = frame.with_columns(
        pl.col("vacancies_000").shift(4).over("region_code").alias("vacancies_lag4"),
        pl.col("quarter_end").cast(pl.Date).alias("month"),
        pl.col("region_code").alias("state_code"),
    ).with_columns(
        (pl.col("vacancies_000") / pl.col("vacancies_lag4") - 1).alias("vacancies_yoy")
    )
    # Carry the quarter forward to each labour month that ends on or after the quarter.
    months = (
        pl.read_parquet(snapshot_dir() / "sa4_month.parquet")
        .select(pl.col("state_code"), _month().alias("month"))
        .unique()
        .sort(["state_code", "month"])
    )
    quarterly = frame.select(
        "state_code", "month", "vacancies_000", "vacancies_yoy"
    ).sort(["state_code", "month"])
    return months.join_asof(quarterly, on="month", by="state_code", strategy="backward")


def _approval_features() -> pl.DataFrame:
    frame = pl.read_parquet(snapshot_dir() / "approvals.parquet")
    frame = frame.filter(pl.col("region_code") != "AUS").sort(["region_code", "month"])
    frame = frame.with_columns(
        _month().alias("month"),
        pl.col("region_code").alias("state_code"),
        pl.col("dwelling_approvals").shift(12).over("region_code").alias("approvals_lag12"),
    )
    return frame.with_columns(
        (pl.col("dwelling_approvals") / pl.col("approvals_lag12") - 1).alias("approvals_yoy"),
        pl.col("dwelling_approvals").alias("approvals"),
    ).select("state_code", "month", "approvals", "approvals_yoy")


def _cash_features() -> pl.DataFrame:
    frame = pl.read_parquet(snapshot_dir() / "cash_rate_month.parquet").sort("month")
    frame = frame.with_columns(_month().alias("month"))
    frame = frame.with_columns(pl.col("cash_rate_target").shift(3).alias("cash_lag3"))
    return frame.with_columns(
        (pl.col("cash_rate_target") - pl.col("cash_lag3")).alias("cash_delta_3"),
        pl.col("cash_rate_target").alias("cash_rate"),
    ).select("month", "cash_rate", "cash_delta_3")


def _state_rate_features() -> pl.DataFrame:
    frame = pl.read_parquet(snapshot_dir() / "state_unemployment.parquet")
    frame = frame.with_columns(_month().alias("month")).sort(["region_code", "month"])
    frame = frame.with_columns(
        pl.col("unemp_rate_sa").shift(3).over("region_code").alias("state_lag3")
    ).with_columns(
        (pl.col("unemp_rate_sa") - pl.col("state_lag3")).alias("state_unemp_delta_3")
    )
    national = frame.filter(pl.col("region_code") == "AUS").select(
        "month",
        pl.col("unemp_rate_sa").alias("aus_rate"),
        pl.col("state_unemp_delta_3").alias("aus_delta"),
    )
    states = frame.filter(pl.col("region_code") != "AUS").select(
        pl.col("region_code").alias("state_code"),
        "month",
        pl.col("unemp_rate_sa").alias("state_unemp_rate"),
        "state_unemp_delta_3",
        pl.lit(1).alias("state_rate_official"),
    )
    # Northern Territory and the ACT are not in this API extract. Use the
    # national seasonally adjusted rate so the column is populated, and flag it.
    missing_states = (
        pl.read_parquet(snapshot_dir() / "sa4_month.parquet")
        .select(pl.col("state_code"), _month().alias("month"))
        .unique()
        .join(states.select("state_code", "month"), on=["state_code", "month"], how="anti")
    )
    filler = missing_states.join(national, on="month", how="left").select(
        "state_code",
        "month",
        pl.col("aus_rate").alias("state_unemp_rate"),
        pl.col("aus_delta").alias("state_unemp_delta_3"),
        pl.lit(0).alias("state_rate_official"),
    )
    return pl.concat([states, filler], how="vertical")


def write_feature_table(frame: pl.DataFrame | None = None) -> Path:
    frame = build_feature_frame() if frame is None else frame
    frame = frame.with_columns([pl.col(column).cast(pl.Float64) for column in FEATURE_COLUMNS])
    feature_dir().mkdir(parents=True, exist_ok=True)
    path = feature_dir() / "sa4_features.parquet"
    frame.write_parquet(path)
    return path


def _feature_view(path: Path):
    from feast import Entity, FeatureView, Field, FileSource
    from feast.data_format import ParquetFormat
    from feast.types import Float64
    from feast.value_type import ValueType

    entity = Entity(
        name="sa4",
        join_keys=[ENTITY],
        value_type=ValueType.STRING,
        description="ABS labour market region code",
    )
    source = FileSource(
        name="sa4_features",
        path=str(path),
        timestamp_field=TIMESTAMP,
        file_format=ParquetFormat(),
        description="Monthly region features. Timestamp is the reference month.",
    )
    view = FeatureView(
        name="sa4_labour",
        entities=[entity],
        ttl=timedelta(days=5000),
        schema=[Field(name=column, dtype=Float64) for column in FEATURE_COLUMNS],
        source=source,
        online=True,
        description="Signals known in the reference month. The next-quarter change is not stored here.",
    )
    return entity, view


def _write_repo_config() -> None:
    feast_dir().mkdir(parents=True, exist_ok=True)
    registry = feast_dir() / "registry.db"
    online = feast_dir() / "online.db"
    text = f"""project: jobs_risk_radar
provider: local
registry: {registry}
online_store:
  type: sqlite
  path: {online}
offline_store:
  type: duckdb
entity_key_serialization_version: 2
"""
    (feast_dir() / "feature_store.yaml").write_text(text)


def retrieve_historical(frame: pl.DataFrame) -> pd.DataFrame:
    """Point-in-time retrieval. The label is joined back afterwards and is not a feature."""
    from feast import FeatureStore

    path = write_feature_table(frame)
    _write_repo_config()
    entity, view = _feature_view(path)
    store = FeatureStore(repo_path=str(feast_dir()))
    store.apply([entity, view])

    entity_df = frame.select(ENTITY, TIMESTAMP).to_pandas()
    entity_df[TIMESTAMP] = pd.to_datetime(entity_df[TIMESTAMP], utc=True)
    feature_refs = [f"sa4_labour:{column}" for column in FEATURE_COLUMNS]
    job = store.get_historical_features(entity_df=entity_df, features=feature_refs)
    retrieved = job.to_df()
    retrieved = _strip_prefixes(retrieved)

    latest = frame.filter(pl.col("month") == frame["month"].max())
    end = pd.Timestamp(latest[TIMESTAMP].max().replace(tzinfo=None)).to_pydatetime()
    start = end - timedelta(days=40)
    store.materialize(start, end + timedelta(days=1))
    online = store.get_online_features(
        features=feature_refs,
        entity_rows=[{ENTITY: code} for code in latest[ENTITY].to_list()],
    ).to_df()
    online = _strip_prefixes(online)
    online_path = feature_dir() / "online_latest.parquet"
    online.to_parquet(online_path, index=False)

    side = frame.select(
        ENTITY,
        TIMESTAMP,
        "sa4_name",
        "state_code",
        "state_name",
        "month",
        "month_num",
        "state_code_num",
        "labour_force",
        "target_delta",
        "unemp_rate",
    ).to_pandas()
    side[TIMESTAMP] = pd.to_datetime(side[TIMESTAMP], utc=True)
    merged = retrieved.merge(side, on=[ENTITY, TIMESTAMP], how="left", suffixes=("", "_direct"))
    merged.to_parquet(feature_dir() / "historical.parquet", index=False)
    _assert_point_in_time(merged)
    return merged


def _strip_prefixes(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for column in frame.columns:
        if column.startswith("sa4_labour__"):
            rename[column] = column.replace("sa4_labour__", "", 1)
        elif column.startswith("sa4_labour:"):
            rename[column] = column.split(":", 1)[1]
    return frame.rename(columns=rename)


def _assert_point_in_time(merged: pd.DataFrame) -> None:
    if "unemp_rate" not in merged.columns or "unemp_rate_direct" not in merged.columns:
        raise RuntimeError(
            "Feast result did not include both the retrieved rate and the reference rate. "
            f"Columns: {list(merged.columns)}"
        )
    gap = (merged["unemp_rate"] - merged["unemp_rate_direct"]).abs().max()
    if pd.isna(gap) or gap > 1e-6:
        raise RuntimeError(f"Point-in-time unemployment rate does not match the reference month ({gap}).")


def latest_cash_override() -> dict[str, float]:
    """Cash rate in force after the latest labour reference month."""
    cash = pl.read_parquet(snapshot_dir() / "cash_rate_month.parquet").sort("month")
    latest = cash.row(-1, named=True)
    earlier = cash.row(-4, named=True)
    return {
        "cash_rate": float(latest["cash_rate_target"]),
        "cash_delta_3": float(latest["cash_rate_target"] - earlier["cash_rate_target"]),
        "cash_month": str(latest["month"])[:10],
    }
