"""Build the DuckDB warehouse with dbt."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from jrr.paths import dbt_dir, root, warehouse_path


def run_dbt() -> None:
    warehouse_path().parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["JRR_ROOT"] = str(root())
    env["JRR_DUCKDB"] = str(warehouse_path())
    dbt_bin = Path(sys.executable).parent / "dbt"
    command = str(dbt_bin) if dbt_bin.exists() else "dbt"
    subprocess.run(
        [
            command,
            "build",
            "--project-dir",
            str(dbt_dir()),
            "--profiles-dir",
            str(dbt_dir()),
        ],
        check=True,
        env=env,
    )
