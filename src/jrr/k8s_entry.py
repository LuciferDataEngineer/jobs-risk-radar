"""Score the snapshot inside the Kubernetes job. Prints a single result line."""

from jrr.forecast import smoke_score


def main() -> None:
    summary = smoke_score()
    print(
        "RADAR_OK "
        f"regions={summary['regions']} "
        f"flagged={summary['flagged']} "
        f"top={summary['top']} "
        f"change={summary['change']:.2f}"
    )


if __name__ == "__main__":
    main()
