import polars as pl

from jrr.features import build_feature_frame
from jrr.paths import snapshot_dir


def test_next_quarter_label_is_not_a_current_feature():
    frame = build_feature_frame()
    sample = frame.filter(
        (pl.col("sa4_code") == "206") & (pl.col("month") == pl.date(2024, 6, 1))
    )
    assert sample.height == 1
    row = sample.row(0, named=True)
    labour = pl.read_parquet(snapshot_dir() / "sa4_month.parquet").with_columns(
        pl.col("month").cast(pl.Date)
    )
    now = labour.filter(
        (pl.col("sa4_code") == "206") & (pl.col("month") == pl.date(2024, 6, 1))
    ).row(0, named=True)
    future = labour.filter(
        (pl.col("sa4_code") == "206") & (pl.col("month") == pl.date(2024, 9, 1))
    ).row(0, named=True)
    past = labour.filter(
        (pl.col("sa4_code") == "206") & (pl.col("month") == pl.date(2023, 6, 1))
    ).row(0, named=True)
    later_past = labour.filter(
        (pl.col("sa4_code") == "206") & (pl.col("month") == pl.date(2023, 9, 1))
    ).row(0, named=True)
    assert abs(row["unemp_rate"] - now["unemp_rate"]) < 1e-9
    assert abs(row["target_delta"] - (future["unemp_rate"] - now["unemp_rate"])) < 1e-9
    assert abs(row["usual_next_quarter_change"] - (later_past["unemp_rate"] - past["unemp_rate"])) < 1e-9
    assert row["unemp_rate"] != future["unemp_rate"] or row["target_delta"] == 0


def test_latest_month_has_no_label_yet():
    frame = build_feature_frame()
    latest = frame.filter(pl.col("month") == frame["month"].max())
    assert latest["target_delta"].null_count() == latest.height
    assert latest["unemp_rate"].null_count() == 0
