import polars as pl

from jrr.paths import snapshot_dir
from jrr.quality import run_quality


def test_quality_gate_passes():
    report = run_quality()
    assert report["regions"] == 87
    assert report["september_2026_national_unemployment_rate"] == 4.71834873


def test_region_months_are_complete():
    frame = pl.read_parquet(snapshot_dir() / "sa4_month.parquet")
    counts = frame.group_by("sa4_code").len()
    assert counts["len"].min() == counts["len"].max()
    assert int(counts["len"][0]) >= 170


def test_cash_rate_path_in_2026():
    cash = pl.read_parquet(snapshot_dir() / "cash_rate_month.parquet").sort("month")
    november = cash.filter(pl.col("month") == pl.datetime(2026, 11, 1))
    september = cash.filter(pl.col("month") == pl.datetime(2026, 9, 1))
    assert float(november["cash_rate_target"][0]) == 4.85
    assert float(september["cash_rate_target"][0]) == 4.6
