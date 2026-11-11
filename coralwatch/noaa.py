
"""
CoralWatch - NOAA Coral Reef Watch v3.1 downloader.

Recent products are downloaded for maps and bleaching alerts.
Historical SST is downloaded separately in chunks for long-term trend analysis.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "noaa"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

FLIGHT_BOUNDS = {
    "PRM2016252225710": (-14.957248, -14.537131, 145.326800, 145.782803),
    "PRM2016266222857": (-19.261510, -18.874604, 152.267841, 152.496945),
    "PRM2016287001832": (-11.460237, -10.737195, 142.756396, 143.959164),
}

RECENT_VARIABLES = [
    "CRW_SST",
    "CRW_SSTANOMALY",
    "CRW_HOTSPOT",
    "CRW_DHW",
    "CRW_BAA_7D_MAX",
]

HISTORY_VARIABLES = ["CRW_SST"]

ERDDAP_ENDPOINTS = [
    (
        "PacIOOS",
        "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km",
    ),
    (
        "NOAA CoastWatch",
        "https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW",
    ),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coralwatch.noaa")


def build_erddap_url(
    bounds,
    days,
    dataset_url,
    variables=None,
    offset=0,
):
    """Build a griddap query for a time chunk relative to the latest record."""
    if days < 1 or days > 365:
        raise ValueError("Each ERDDAP request must contain 1 to 365 days.")

    south, north, west, east = bounds
    variables = variables or RECENT_VARIABLES

    first_index = offset + days - 1
    last_index = offset

    if last_index == 0:
        time_constraint = f"[last-{first_index}:1:last]"
    else:
        time_constraint = (
            f"[last-{first_index}:1:last-{last_index}]"
        )

    latitude_constraint = f"[({north}):1:({south})]"
    longitude_constraint = f"[({west}):1:({east})]"

    selections = ",".join(
        f"{name}{time_constraint}{latitude_constraint}{longitude_constraint}"
        for name in variables
    )

    return (
        f"{dataset_url}.nc?"
        f"{quote(selections, safe='[]():,.*-')}"
    )


def is_netcdf(path):
    with path.open("rb") as file:
        signature = file.read(8)

    return (
        signature.startswith(b"CDF")
        or signature == b"\x89HDF\r\n\x1a\n"
    )


def download_request(
    flight_id,
    bounds,
    days,
    output_path,
    variables,
    offset=0,
    refresh=False,
):
    """Download one time chunk, trying the available ERDDAP mirrors."""
    if output_path.exists() and output_path.stat().st_size > 0 and not refresh:
        logger.info("Using cached file: %s", output_path.name)
        return output_path

    errors = []

    for server_name, base_url in ERDDAP_ENDPOINTS:
        url = build_erddap_url(
            bounds=bounds,
            days=days,
            dataset_url=base_url,
            variables=variables,
            offset=offset,
        )

        partial_path = output_path.with_suffix(output_path.suffix + ".part")
        logger.info(
            "Requesting %s | %s | %s days | offset %s",
            server_name,
            flight_id,
            days,
            offset,
        )

        try:
            with requests.get(
                url,
                stream=True,
                timeout=(30, 600),
                headers={
                    "User-Agent": "CoralWatch/1.0 (NASA Space Apps educational project)"
                },
            ) as response:
                if response.status_code >= 400:
                    detail = response.text[:2000]
                    raise RuntimeError(
                        f"HTTP {response.status_code}: {detail}"
                    )

                with partial_path.open("wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            file.write(chunk)

            if not partial_path.exists() or partial_path.stat().st_size < 100:
                raise RuntimeError("The server returned an empty response.")

            if not is_netcdf(partial_path):
                preview = partial_path.read_bytes()[:300].decode(
                    "utf-8", errors="replace"
                )
                raise RuntimeError(
                    f"The server did not return a valid NetCDF file: {preview}"
                )

            partial_path.replace(output_path)

            logger.info(
                "Downloaded %s (%.2f MB)",
                output_path.name,
                output_path.stat().st_size / (1024 * 1024),
            )
            return output_path

        except Exception as exc:
            errors.append(f"{server_name}: {exc}")
            logger.warning("%s failed: %s", server_name, exc)
            partial_path.unlink(missing_ok=True)
            time.sleep(2)

    raise RuntimeError(
        f"Could not download NOAA data for {flight_id}.\n"
        + "\n".join(errors)
    )


def download_subset(flight_id, bounds, days=30, refresh=False):
    """Download the recent multi-variable NOAA time series."""
    if days < 1 or days > 365:
        raise ValueError("Recent downloads must be between 1 and 365 days.")

    output_path = RAW_DIR / f"{flight_id}_NOAA_last_{days}_days.nc"

    return download_request(
        flight_id=flight_id,
        bounds=bounds,
        days=days,
        output_path=output_path,
        variables=RECENT_VARIABLES,
        offset=0,
        refresh=refresh,
    )


def download_sst_history(
    flight_id,
    bounds,
    history_days=15000,
    chunk_days=365,
    refresh=False,
):
    """Download historical SST, retrying failed chunks with smaller intervals."""

    if history_days < 1 or history_days > 15000:
        raise ValueError("history_days must be between 1 and 15000.")

    if chunk_days < 1 or chunk_days > 365:
        raise ValueError("chunk_days must be between 1 and 365.")

    downloaded = []
    failed_chunks = []

    def download_chunk(offset, days):
        """Try one chunk and recursively split it if the request fails."""

        output_path = RAW_DIR / (
            f"{flight_id}_NOAA_SST_history_"
            f"offset_{offset:05d}_days_{days:03d}.nc"
        )

        try:
            path = download_request(
                flight_id=flight_id,
                bounds=bounds,
                days=days,
                output_path=output_path,
                variables=HISTORY_VARIABLES,
                offset=offset,
                refresh=refresh,
            )

            downloaded.append(path)

            # Avoid sending requests too rapidly to the public ERDDAP service.
            time.sleep(1.5)

        except Exception as exc:

            if days <= 30:
                logger.error(
                    "Historical chunk failed permanently | "
                    "%s | offset %s | %s days",
                    flight_id,
                    offset,
                    days,
                )

                failed_chunks.append(
                    f"offset={offset}, days={days}: {exc}"
                )
                return

            if days > 90:
                smaller_chunk = 90
            else:
                smaller_chunk = 30

            logger.warning(
                "Retrying with smaller chunks | %s | "
                "offset %s | %s days -> %s days",
                flight_id,
                offset,
                days,
                smaller_chunk,
            )

            for sub_offset in range(
                offset,
                offset + days,
                smaller_chunk,
            ):
                sub_days = min(
                    smaller_chunk,
                    offset + days - sub_offset,
                )

                download_chunk(sub_offset, sub_days)

    for offset in range(0, history_days, chunk_days):
        current_days = min(
            chunk_days,
            history_days - offset,
        )

        download_chunk(offset, current_days)

    if failed_chunks:
        logger.warning(
            "%s historical chunks could not be downloaded for %s.",
            len(failed_chunks),
            flight_id,
        )

        raise RuntimeError(
            f"Some historical chunks could not be downloaded "
            f"for {flight_id}:\n"
            + "\n".join(failed_chunks)
        )

    logger.info(
        "Historical download completed for %s: %s files.",
        flight_id,
        len(downloaded),
    )

    return downloaded


def bounds_from_catalog(flight_catalog):
    """Use NASA flight bounds when available; otherwise use the sample bounds."""
    if flight_catalog is None or flight_catalog.empty:
        return FLIGHT_BOUNDS.copy()

    required = {
        "flight_line",
        "latitude_min",
        "latitude_max",
        "longitude_min",
        "longitude_max",
    }

    if not required.issubset(flight_catalog.columns):
        return FLIGHT_BOUNDS.copy()

    result = {}

    for _, row in flight_catalog.iterrows():
        values = [
            row["latitude_min"],
            row["latitude_max"],
            row["longitude_min"],
            row["longitude_max"],
        ]

        if any(value is None for value in values):
            continue

        try:
            lat_min, lat_max, lon_min, lon_max = map(float, values)
        except (TypeError, ValueError):
            continue

        if not (-90 <= lat_min <= lat_max <= 90):
            continue
        if not (-180 <= lon_min <= lon_max <= 180):
            continue

        # Expand the footprint slightly to include nearby 5-km grid cells.
        padding = 0.05
        flight_id = str(row["flight_line"]).strip()

        result[flight_id] = (
            lat_min - padding,
            lat_max + padding,
            lon_min - padding,
            lon_max + padding,
        )

    return result or FLIGHT_BOUNDS.copy()


def process_noaa_data(flight_catalog=None, use_existing_file=None):
    """
    Compatibility function used by coralwatch.pipeline.

    Downloads recent data, then creates daily summaries and the latest pixel map.
    """
    from . import settings
    from .noaa_analysis import analyze_recent_files

    if use_existing_file is not None:
        files = [Path(use_existing_file)]
        if not files[0].exists():
            raise FileNotFoundError(files[0])
    else:
        bounds_by_region = bounds_from_catalog(flight_catalog)
        days = min(max(int(settings.NOAA_DAYS), 1), 365)

        files = []
        for flight_id, bounds in bounds_by_region.items():
            files.append(
                download_subset(
                    flight_id,
                    bounds,
                    days=days,
                    refresh=False,
                )
            )

    analyze_recent_files(files)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Download NOAA Coral Reef Watch v3.1 data for CoralWatch."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Recent multi-variable time series length (1-365 days).",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=0,
        help="Historical SST time series length (up to 15000 days).",
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=365,
        help="Historical request size (maximum 365 days).",
    )
    parser.add_argument(
        "--skip-recent",
        action="store_true",
        help="Skip the recent multi-variable download.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Download again even when cached files exist.",
    )
    args = parser.parse_args()

    if not args.skip_recent and not 1 <= args.days <= 365:
        parser.error("--days must be between 1 and 365.")

    if not 0 <= args.history_days <= 15000:
        parser.error("--history-days must be between 0 and 15000.")

    if not 1 <= args.chunk_days <= 365:
        parser.error("--chunk-days must be between 1 and 365.")

    results = []

    if not args.skip_recent:
        for flight_id, bounds in FLIGHT_BOUNDS.items():
            try:
                path = download_subset(
                    flight_id,
                    bounds,
                    days=args.days,
                    refresh=args.refresh,
                )
                results.append(
                    {
                        "flight_id": flight_id,
                        "file": str(path.relative_to(PROJECT_ROOT)),
                        "status": "recent_downloaded_or_cached",
                    }
                )
            except Exception as exc:
                logger.error("%s", exc)
                results.append(
                    {
                        "flight_id": flight_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

    if args.history_days:
        for flight_id, bounds in FLIGHT_BOUNDS.items():
            try:
                files = download_sst_history(
                    flight_id,
                    bounds,
                    history_days=args.history_days,
                    chunk_days=args.chunk_days,
                    refresh=args.refresh,
                )
                results.append(
                    {
                        "flight_id": flight_id,
                        "history_files": len(files),
                        "status": "historical_sst_downloaded_or_cached",
                    }
                )
            except Exception as exc:
                logger.error("%s", exc)
                results.append(
                    {
                        "flight_id": flight_id,
                        "status": "historical_download_failed",
                        "error": str(exc),
                    }
                )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "product": "NOAA Coral Reef Watch v3.1 daily global 5-km",
        "recent_variables": RECENT_VARIABLES,
        "historical_variables": HISTORY_VARIABLES,
        "history_days_requested": args.history_days,
        "chunk_days": args.chunk_days,
        "results": results,
    }

    report_path = OUTPUT_DIR / "noaa_download_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    from .noaa_analysis import run_analysis

    run_analysis()

    logger.info("Download report: %s", report_path)


if __name__ == "__main__":
    main()
