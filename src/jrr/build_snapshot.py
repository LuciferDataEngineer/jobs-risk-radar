"""Build the committed snapshot from the free source files.

The raw workbooks are not stored in git. Re-run with ``JRR_RAW`` pointing at a
folder of downloads, or pass ``--download`` to fetch them again.

Jobs and Skills Australia's Internet Vacancy Index host did not respond from
this environment (connection timed out, then HTTP/2 internal error). Regional
vacancy pressure is therefore taken from the ABS Job Vacancies series by state,
which is free and CC BY 4.0. See the manifest note.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from datetime import date
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd
import polars as pl

from jrr.columns import STATE_NAMES
from jrr.paths import boundary_path, root, snapshot_dir

ACCESS_DATE = "2026-11-09"

ABS_MLF = (
    "https://www.abs.gov.au/statistics/labour/employment-and-unemployment/"
    "regional-labour-force/sep-2026/MLF1.xlsx"
)
ABS_LF_STATES = (
    "https://data.api.abs.gov.au/rest/data/LF/"
    "M13.3.1599.20.AUS+1+2+3+4+5+6+7+8.M?startPeriod=2012-01&format=csv"
)
ABS_JV = (
    "https://data.api.abs.gov.au/rest/data/JV/"
    "M1.7.TOT.10.1+2+3+4+5+6+7+8+AUS.Q?startPeriod=2012-Q1&format=csv"
)
ABS_BA = (
    "https://data.api.abs.gov.au/rest/data/BA_GCCSA/"
    "1.1.9.TOT.TOT.10.1+2+3+4+5+6+7+8+AUS.M?startPeriod=2015-01&format=csv"
)
ABS_SA4_ZIP = (
    "https://www.abs.gov.au/statistics/standards/"
    "australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/"
    "access-and-downloads/digital-boundary-files/SA4_2021_AUST_SHP_GDA2020.zip"
)
RBA_F1 = "https://www.rba.gov.au/statistics/tables/xls/f01d.xlsx"

CC_BY = "CC BY 4.0"
RBA_NOTE = (
    "RBA Statistical Table F1 series FIRMMCRTD (cash rate target). "
    "Only this RBA series was copied. Other F1 columns, including bank-bill and "
    "swap rates sourced from ASX and market vendors, were not copied. "
    "The RBA permits reproduction of its website statistics with attribution; "
    "this series is not a third-party market yield."
)


def _raw_dir() -> Path:
    override = os.environ.get("JRR_RAW")
    if override:
        return Path(override)
    return root() / "data" / "raw"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    urlretrieve(url, dest)  # noqa: S310 - fixed public statistical URLs


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _region_parts(label: str) -> tuple[str, str]:
    code, name = str(label).split(" ", 1)
    return code, name.strip()


def build_sa4(mlf_path: Path) -> pl.DataFrame:
    frame = pd.read_excel(mlf_path, sheet_name="Data 1", header=3)
    frame = frame.rename(
        columns={
            "Month": "month",
            "Sex": "sex",
            "Age": "age",
            "Labour market region (SA4): ASGS (2011)": "region",
            "Employed total ('000)": "employed",
            "Unemployed total ('000)": "unemployed",
            "Not in the labour force (NILF) ('000)": "nilf",
        }
    )
    keep = ["month", "sex", "age", "region", "employed", "unemployed", "nilf"]
    frame = frame[keep].dropna(subset=["region", "month"])
    parsed = frame["region"].map(_region_parts)
    frame["sa4_code"] = parsed.map(lambda item: item[0])
    frame["sa4_name"] = parsed.map(lambda item: item[1])
    frame["state_code"] = frame["sa4_code"].str[0]
    youth = frame[frame["age"] == "15-24 years"]
    total = (
        frame.groupby(["month", "sa4_code", "sa4_name", "state_code"], as_index=False)[
            ["employed", "unemployed", "nilf"]
        ].sum()
    )
    youth_sum = youth.groupby(["month", "sa4_code"], as_index=False)[
        ["employed", "unemployed"]
    ].sum()
    youth_sum = youth_sum.rename(
        columns={"employed": "youth_employed", "unemployed": "youth_unemployed"}
    )
    merged = total.merge(youth_sum, on=["month", "sa4_code"], how="left")
    data = pl.from_pandas(merged).with_columns(
        pl.col("month").cast(pl.Datetime("us")),
        pl.col("state_code").replace_strict(STATE_NAMES).alias("state_name"),
    )
    data = data.with_columns(
        (pl.col("employed") + pl.col("unemployed")).alias("labour_force"),
        (pl.col("youth_employed") + pl.col("youth_unemployed")).alias("youth_labour_force"),
    )
    data = data.with_columns(
        (100 * pl.col("unemployed") / pl.col("labour_force")).alias("unemp_rate"),
        (
            100
            * pl.col("labour_force")
            / (pl.col("labour_force") + pl.col("nilf"))
        ).alias("participation_rate"),
        (100 * pl.col("youth_unemployed") / pl.col("youth_labour_force")).alias(
            "youth_unemp_rate"
        ),
    )
    return data.sort(["sa4_code", "month"])


def build_state_unemployment(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, schema_overrides={"REGION": pl.Utf8}).select(
        pl.col("REGION").cast(pl.Utf8).alias("region_code"),
        pl.col("TIME_PERIOD").str.to_date("%Y-%m").alias("month"),
        pl.col("OBS_VALUE").alias("unemp_rate_sa"),
    )
    return frame.with_columns(
        pl.col("region_code").replace_strict(STATE_NAMES, default=None).alias("region_name")
    ).sort(["region_code", "month"])


def _quarter_end(label: str) -> date:
    year, quarter = label.split("-Q")
    month = int(quarter) * 3
    return date(int(year), month, 1)


def build_vacancies(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, schema_overrides={"REGION": pl.Utf8, "TSEST": pl.Utf8})
    if "TSEST" in frame.columns:
        frame = frame.filter(pl.col("TSEST").cast(pl.Utf8) == "10")
    out = frame.select(
        pl.col("REGION").cast(pl.Utf8).alias("region_code"),
        pl.col("TIME_PERIOD").alias("quarter"),
        pl.col("OBS_VALUE").alias("vacancies_000"),
    )
    ends = [_quarter_end(value) for value in out["quarter"].to_list()]
    return out.with_columns(
        pl.Series("quarter_end", ends).cast(pl.Date),
        pl.col("region_code").replace_strict(STATE_NAMES, default=None).alias("region_name"),
    ).sort(["region_code", "quarter_end"])


def build_approvals(path: Path) -> pl.DataFrame:
    frame = pl.read_csv(path, schema_overrides={"REGION": pl.Utf8}).select(
        pl.col("REGION").cast(pl.Utf8).alias("region_code"),
        pl.col("TIME_PERIOD").str.to_date("%Y-%m").alias("month"),
        pl.col("OBS_VALUE").alias("dwelling_approvals"),
    )
    return frame.with_columns(
        pl.col("region_code").replace_strict(STATE_NAMES, default=None).alias("region_name")
    ).sort(["region_code", "month"])


def build_cash_rate(path: Path) -> pl.DataFrame:
    """Keep only the RBA cash-rate target. Do not copy other F1 columns."""
    sheet = pd.read_excel(path, sheet_name="Data", header=None)
    header_idx = sheet.index[sheet.iloc[:, 0].astype(str).eq("Series ID")]
    if len(header_idx) != 1:
        raise RuntimeError("Could not find the Series ID row in RBA F1.")
    start = int(header_idx[0]) + 1
    daily = sheet.iloc[start:, [0, 1]].copy()
    daily.columns = ["date", "cash_rate_target"]
    daily = daily.dropna(subset=["date"])
    daily["cash_rate_target"] = pd.to_numeric(daily["cash_rate_target"], errors="coerce")
    daily = daily.dropna(subset=["cash_rate_target"])
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date")
    monthly = (
        daily.assign(month=daily["date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month", as_index=False)
        .tail(1)
    )
    monthly = monthly[["month", "cash_rate_target"]].rename(columns={"month": "month"})
    return pl.from_pandas(monthly).with_columns(pl.col("month").cast(pl.Datetime("us")))


def _round_coords(obj: object, digits: int = 3) -> object:
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(value), digits) for value in obj]
        return [_round_coords(item, digits) for item in obj]
    return obj


def build_boundaries(zip_path: Path, dest: Path) -> None:
    import shapefile
    from shapely.geometry import shape
    from shapely.ops import unary_union

    extract_dir = zip_path.parent / "sa4_shp"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    shp = next(extract_dir.glob("SA4_2021_AUST_GDA2020.shp"))
    reader = shapefile.Reader(str(shp))
    outback_parts = []
    features = []
    for record, shp_rec in zip(reader.records(), reader.shapes(), strict=True):
        code = str(record["SA4_CODE21"])
        if code in {"ZZZ"} or code.endswith("97") or code.endswith("99") or code.startswith("9"):
            continue
        geom = shape(shp_rec.__geo_interface__)
        if code in {"510", "511"}:
            outback_parts.append(geom)
            continue
        features.append(_feature(code, code, str(record["SA4_NAME21"]), geom))
    if len(outback_parts) == 2:
        merged = unary_union(outback_parts).simplify(0.04, preserve_topology=True)
        features.append(
            _feature(
                "508",
                "508",
                "Western Australia - Outback (North and South)",
                merged,
            )
        )
    collection = {"type": "FeatureCollection", "features": features}
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(collection, separators=(",", ":")))


def _feature(code: str, radar_code: str, name: str, geom: object) -> dict:
    from shapely.geometry import mapping

    simplified = geom.simplify(0.04, preserve_topology=True)
    geometry = mapping(simplified)
    geometry["coordinates"] = _round_coords(geometry["coordinates"])
    return {
        "type": "Feature",
        "properties": {
            "sa4_code": code,
            "radar_code": radar_code,
            "name": name,
            "state_code": code[0],
            "state_name": STATE_NAMES.get(code[0], ""),
        },
        "geometry": geometry,
    }


def _write(frame: pl.DataFrame, name: str) -> dict:
    dest = snapshot_dir() / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(dest)
    return {
        "path": f"data/snapshot/{name}",
        "rows": frame.height,
        "columns": frame.columns,
        "sha256": _sha256(dest),
        "bytes": dest.stat().st_size,
    }


def build(download: bool = False) -> dict:
    raw = _raw_dir()
    raw.mkdir(parents=True, exist_ok=True)
    files = {
        "mlf": raw / "MLF1.xlsx",
        "states": raw / "lf_states.csv",
        "vacancies": raw / "jv_hist.csv",
        "approvals": raw / "ba_hist.csv",
        "cash": raw / "f01d.xlsx",
        "boundaries": raw / "sa4.zip",
    }
    urls = {
        "mlf": ABS_MLF,
        "states": ABS_LF_STATES,
        "vacancies": ABS_JV,
        "approvals": ABS_BA,
        "cash": RBA_F1,
        "boundaries": ABS_SA4_ZIP,
    }
    if download:
        for key, url in urls.items():
            _download(url, files[key])
    for key, path in files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing {path}. Set JRR_RAW or pass --download.")

    files_meta = {
        "sa4_month.parquet": _write(build_sa4(files["mlf"]), "sa4_month.parquet"),
        "state_unemployment.parquet": _write(
            build_state_unemployment(files["states"]), "state_unemployment.parquet"
        ),
        "vacancies.parquet": _write(build_vacancies(files["vacancies"]), "vacancies.parquet"),
        "approvals.parquet": _write(build_approvals(files["approvals"]), "approvals.parquet"),
        "cash_rate_month.parquet": _write(build_cash_rate(files["cash"]), "cash_rate_month.parquet"),
    }
    build_boundaries(files["boundaries"], boundary_path())
    boundary_meta = {
        "path": "data/boundaries/sa4.geojson",
        "sha256": _sha256(boundary_path()),
        "bytes": boundary_path().stat().st_size,
    }
    manifest = {
        "access_date": ACCESS_DATE,
        "access_timezone": "Australia/Melbourne",
        "files": files_meta,
        "boundaries": boundary_meta,
        "sources": [
            {
                "name": "ABS Regional Labour Force, modelled SA4 estimates",
                "publisher": "Australian Bureau of Statistics",
                "url": "https://www.abs.gov.au/statistics/labour/employment-and-unemployment/regional-labour-force/sep-2026",
                "download_url": ABS_MLF,
                "licence": CC_BY,
                "coverage": "87 labour market regions, January 2012 to September 2026, persons by age and sex rolled up",
                "free": True,
                "note": (
                    "First issue of Regional Labour Force, released 22 October 2026. "
                    "The cube header still says ASGS 2011, but the region list matches "
                    "ASGS Edition 3 with Western Australia - Outback (North) and (South) "
                    "published as one combined region, code 508, as the ABS release notes."
                ),
            },
            {
                "name": "ABS Labour Force, unemployment rate by state",
                "publisher": "Australian Bureau of Statistics",
                "url": "https://www.abs.gov.au/statistics/labour/employment-and-unemployment/labour-force-australia/sep-2026",
                "download_url": ABS_LF_STATES,
                "licence": CC_BY,
                "coverage": "Seasonally adjusted unemployment rate, persons aged 15 and over, Australia and states 1-6, January 2012 to September 2026",
                "free": True,
                "note": (
                    "Data API dataflow LF, key M13 (unemployment rate), sex 3, age 1599, "
                    "TSEST 20, monthly. Region codes 7 and 8 (Northern Territory and "
                    "Australian Capital Territory) returned no records for this key, so "
                    "those two jurisdictions are read from the modelled SA4 estimates."
                ),
            },
            {
                "name": "ABS Job Vacancies by state",
                "publisher": "Australian Bureau of Statistics",
                "url": "https://www.abs.gov.au/statistics/labour/jobs/job-vacancies-australia/latest-release",
                "download_url": ABS_JV,
                "licence": CC_BY,
                "coverage": "Original job vacancies, total sectors and industries, states and Australia, 2012 Q1 to 2026 Q3, thousands",
                "free": True,
                "note": (
                    "Substitute for the Jobs and Skills Australia Internet Vacancy Index. "
                    "The JSA download host did not return the September 2026 SA4 workbook "
                    "(timed out, then HTTP/2 internal error) on 9 November 2026. "
                    "ABS vacancies are quarterly and state-level, not SA4 job ads."
                ),
            },
            {
                "name": "ABS Building Approvals, dwelling units by state",
                "publisher": "Australian Bureau of Statistics",
                "url": "https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/latest-release",
                "download_url": ABS_BA,
                "licence": CC_BY,
                "coverage": "Number of dwelling units approved, total sectors, total residential, states and Australia, January 2015 to September 2026",
                "free": True,
                "note": "Data API dataflow BA_GCCSA, measure 1, value 1, sector 9, work type TOT, building type TOT, original.",
            },
            {
                "name": "RBA cash rate target",
                "publisher": "Reserve Bank of Australia",
                "url": "https://www.rba.gov.au/statistics/cash-rate/",
                "download_url": RBA_F1,
                "licence": "RBA website statistics, attribution required; see note",
                "coverage": "Cash rate target on the last published day of each month, from the daily F1 target series through 6 November 2026",
                "free": True,
                "note": RBA_NOTE,
            },
            {
                "name": "ASGS Edition 3 SA4 digital boundaries",
                "publisher": "Australian Bureau of Statistics",
                "url": "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/digital-boundary-files",
                "download_url": ABS_SA4_ZIP,
                "licence": CC_BY,
                "coverage": "SA4 2021 boundaries, simplified for the web map. Outback North and South dissolved to region 508.",
                "free": True,
                "note": "Coastlines are simplified. This is a display file, not a legal boundary.",
            },
        ],
    }
    manifest_path = root() / "data" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the jobs-risk-radar snapshot")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    manifest = build(download=args.download)
    for name, meta in manifest["files"].items():
        print(f"{name}: {meta['rows']} rows")
    print(f"boundaries: {manifest['boundaries']['bytes']} bytes")


if __name__ == "__main__":
    main()
