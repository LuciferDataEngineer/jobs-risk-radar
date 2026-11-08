"""Run the radar from the committed snapshot through to the stakeholder pages."""

from __future__ import annotations

from jrr.dashboard import build_site
from jrr.drift import build_drift
from jrr.features import build_feature_frame, retrieve_historical
from jrr.model import train_and_track
from jrr.quality import run_quality
from jrr.warehouse import run_dbt


def run() -> dict:
    quality = run_quality()
    run_dbt()
    frame = build_feature_frame()
    historical = retrieve_historical(frame)
    tracked = train_and_track(historical)
    drift = build_drift(historical, tracked["predictions"])
    headlines = build_site(tracked["scores"], tracked["summary"])
    return {"quality": quality, "drift": drift, "headlines": headlines}


def main() -> None:
    result = run()
    headlines = result["headlines"]
    print(
        f"RADAR_OK regions={headlines['regions']} flagged={headlines['flagged']} "
        f"top={headlines['top_region']}"
    )


if __name__ == "__main__":
    main()
