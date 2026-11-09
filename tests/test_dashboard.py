from pathlib import Path

from jrr.paths import root

BANNED = [
    "feast",
    "mlflow",
    "evidently",
    "dagster",
    "duckdb",
    "lightgbm",
    "kubernetes",
    "terraform",
    "parquet",
    "schema",
    "pipeline",
    "backtest",
    "feature store",
    "drift",
    "classifier",
    "regression",
    "baseline",
    "seasonally",
]


def test_pages_are_plain_language():
    page = Path(root() / "site" / "index.html").read_text(encoding="utf-8").lower()
    for word in BANNED:
        assert word not in page, word
    for label in ["Overview", "Regions map", "Who's at risk", "What to do"]:
        assert label in Path(root() / "site" / "index.html").read_text(encoding="utf-8")
    assert "australia/melbourne" in page or "aedt" in page or "aest" in page
    assert "exact chart values" in page
    assert "state-filter" in page
    assert "all states" in page
    assert "https://github.com/luciferdataengineer/jobs-risk-radar" in page
    assert "chart.resize()" in page
    assert "#0c0c0e" in page
    assert (root() / "site" / "drift" / "index.html").exists()
    assert (root() / "site" / "sa4.geojson").exists()


def test_dagster_graph_has_the_stages():
    from jrr.definitions import defs

    names = {asset.key.to_user_string() for asset in defs.assets}
    assert {
        "checked_snapshot",
        "warehouse",
        "historical_features",
        "scored_regions",
        "drift_report",
        "stakeholder_site",
    } <= names
