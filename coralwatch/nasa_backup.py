"""Process NASA CORAL/PRISM L2 NetCDF files for the CoralWatch dashboard.

The CORAL files store scientific variables in NetCDF groups:
- /derived_data: coral, algae, sand, GPP, G, Kd, ...
- /navigation_data: latitude, longitude, ...

This module reads the large 2-D arrays in scan-line chunks so it does not
need to load an entire multi-GB file into RAM.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from . import settings


# Variables used for composition statistics. These exist in the files inspected.
SUMMARY_VARIABLES = ("coral", "algae", "sand", "GPP", "G")

# Only these three probability layers are exported as map points by default.
SPATIAL_VARIABLES = ("coral", "algae", "sand")

SPATIAL_COLUMNS = [
    "latitude",
    "longitude",
    "value",
    "source_file",
    "region",
    "observation_date",
    "variable",
    "units",
    "sampled_for_size",
]

SPATIAL_QUALITY_COLUMNS = [
    "latitude",
    "longitude",
    "source_file",
    "flight_line",
    "region",
    "observation_date",
    "is_benthic_valid",
    "quality_status",
    "coral_probability",
    "algae_probability",
    "sand_probability",
    "probability_sum",
    "sampled_for_size",
]

QUALITY_CLASS_VARIABLES = ("coral", "algae", "sand")

LEGEND_ROWS = [
    {
        "variable": "coral",
        "display_name": "Coral",
        "meaning": "Probability of coral benthic cover type",
        "units": "unitless",
        "interpretation": "Per-pixel model probability, from 0 to 1; not a direct diagnosis of coral health.",
    },
    {
        "variable": "algae",
        "display_name": "Algae",
        "meaning": "Probability of algae benthic cover type",
        "units": "unitless",
        "interpretation": "Per-pixel model probability, from 0 to 1.",
    },
    {
        "variable": "sand",
        "display_name": "Sand",
        "meaning": "Probability of sand benthic cover type",
        "units": "unitless",
        "interpretation": "Per-pixel model probability, from 0 to 1.",
    },
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _path_setting(name: str, fallback: Path) -> Path:
    return Path(getattr(settings, name, fallback))


def _directories() -> dict[str, Path]:
    root = _project_root()
    return {
        "nasa_raw": _path_setting("NASA_RAW_DIR", root / "data" / "raw" / "nasa"),
        "noaa_raw": _path_setting("NOAA_RAW_DIR", root / "data" / "raw" / "noaa"),
        "processed": _path_setting("PROCESSED_DIR", root / "data" / "processed"),
        "logs": _path_setting("LOG_DIR", root / "logs"),
        "downloads": _path_setting("DOWNLOADS_DIR", root / "downloads"),
    }


def ensure_directories() -> dict[str, Path]:
    directories = _directories()
    for directory in directories.values():
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def safe_attr(value: Any) -> str:
    """Convert NetCDF attribute values to strings safe for CSV/JSON."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, np.integer, np.floating)):
        return str(value)
    if isinstance(value, (list, tuple, np.ndarray)):
        return ", ".join(map(str, np.asarray(value).ravel()[:30]))
    return str(value)


def _attribute(obj: Any, name: str, default: Any = None) -> Any:
    """Read a NetCDF attribute without raising when it is absent."""
    if name in obj.ncattrs():
        return obj.getncattr(name)
    return default


def _read_float_block(variable: Any, start: int, end: int) -> np.ndarray:
    """Read a 2-D variable block and convert masked/invalid cells to NaN."""
    block = variable[start:end, :]

    if np.ma.isMaskedArray(block):
        block = block.filled(np.nan)

    values = np.asarray(block, dtype=np.float32)
    values[~np.isfinite(values)] = np.nan

    # Respect valid_min/valid_max metadata when present.
    valid_min = _attribute(variable, "valid_min")
    valid_max = _attribute(variable, "valid_max")
    if valid_min is not None:
        values[values < float(valid_min)] = np.nan
    if valid_max is not None:
        values[values > float(valid_max)] = np.nan

    return values


def _global_attributes(dataset: Dataset) -> dict[str, str]:
    return {
        str(name): safe_attr(dataset.getncattr(name))
        for name in dataset.ncattrs()
    }


def _variable_inventory(dataset: Dataset, source_file: str) -> list[dict[str, Any]]:
    """Collect metadata only; do not read the large scientific arrays."""
    rows: list[dict[str, Any]] = []

    for group_name, group in dataset.groups.items():
        for variable_name, variable in group.variables.items():
            rows.append(
                {
                    "source_file": source_file,
                    "group": group_name,
                    "variable": variable_name,
                    "full_name": f"/{group_name}/{variable_name}",
                    "dimensions": ",".join(variable.dimensions),
                    "shape": " x ".join(map(str, variable.shape)),
                    "dtype": str(variable.dtype),
                    "units": safe_attr(_attribute(variable, "units", "")),
                    "long_name": safe_attr(_attribute(variable, "long_name", "")),
                    "valid_min": safe_attr(_attribute(variable, "valid_min", "")),
                    "valid_max": safe_attr(_attribute(variable, "valid_max", "")),
                }
            )

    return rows


def _mean_from_sums(total_sum: float, count: int) -> float:
    return float(total_sum / count) if count else float("nan")


def _process_one_file(
    path: Path,
    region_name: str,
    chunk_scans: int,
    max_spatial_rows: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[pd.DataFrame],
    list[pd.DataFrame],
]:
    """Process one CORAL NetCDF file in scan-line chunks."""
    variable_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    spatial_parts: list[pd.DataFrame] = []
    spatial_quality_parts: list[pd.DataFrame] = []

    with Dataset(path, mode="r") as dataset:
        if "derived_data" not in dataset.groups or "navigation_data" not in dataset.groups:
            raise ValueError(
                f"{path.name} não contém os grupos derived_data e navigation_data esperados."
            )

        derived = dataset.groups["derived_data"]
        navigation = dataset.groups["navigation_data"]

        required = ("coral", "algae", "sand")
        missing = [name for name in required if name not in derived.variables]
        if missing:
            raise ValueError(f"Variáveis bentônicas ausentes em {path.name}: {missing}")

        for coordinate_name in ("latitude", "longitude"):
            if coordinate_name not in navigation.variables:
                raise ValueError(f"Variável {coordinate_name} ausente em {path.name}.")

        coral_var = derived.variables["coral"]
        n_scans, n_pixels = coral_var.shape
        total_pixels = int(n_scans) * int(n_pixels)

        # Choose a regular grid so the map CSV stays small.
        spatial_step = max(1, int(math.ceil(math.sqrt(total_pixels / max(1, max_spatial_rows)))))

        observation_date = safe_attr(_attribute(dataset, "time_coverage_start", ""))
        flight_line = safe_attr(_attribute(dataset, "flight_line", path.stem))
        lat_min = _attribute(dataset, "geospatial_lat_min", _attribute(dataset, "southernmost_latitude", np.nan))
        lat_max = _attribute(dataset, "geospatial_lat_max", _attribute(dataset, "northernmost_latitude", np.nan))
        lon_min = _attribute(dataset, "geospatial_lon_min", _attribute(dataset, "westernmost_longitude", np.nan))
        lon_max = _attribute(dataset, "geospatial_lon_max", _attribute(dataset, "easternmost_longitude", np.nan))

        catalog_row = {
            "source_file": path.name,
            "flight_line": flight_line,
            "region": region_name,
            "observation_date": observation_date,
            "latitude_min": float(lat_min) if lat_min is not None else np.nan,
            "latitude_max": float(lat_max) if lat_max is not None else np.nan,
            "longitude_min": float(lon_min) if lon_min is not None else np.nan,
            "longitude_max": float(lon_max) if lon_max is not None else np.nan,
            "number_of_scans": int(n_scans),
            "pixels_per_scan": int(n_pixels),
            "spatial_resolution": safe_attr(_attribute(dataset, "spatialResolution", "")),
            "processing_level": safe_attr(_attribute(dataset, "processing_level", "")),
        }

        inventory_row = {
            "source_file": path.name,
            "file_size_gb": round(path.stat().st_size / (1024 ** 3), 3),
            "dimensions": json.dumps(
                {name: len(dimension) for name, dimension in dataset.dimensions.items()}
            ),
            "groups": ",".join(dataset.groups.keys()),
            "region_selected": region_name,
            "global_attributes": json.dumps(_global_attributes(dataset), ensure_ascii=False),
        }

        variable_rows.extend(_variable_inventory(dataset, path.name))

        # Quality counters are computed over every pixel, in chunks.
        quality_counts = {name: 0 for name in QUALITY_CLASS_VARIABLES}
        valid_benthic_pixels = 0
        valid_geolocation_pixels = 0
        valid_benthic_geolocation_pixels = 0
        spatial_quality_sample_points = 0
        probability_sum_count = 0
        probability_sum_total = 0.0
        probability_sum_min = np.inf
        probability_sum_max = -np.inf
        probability_sum_in_range_count = 0

        # Calculate full-data statistics but retain only a small spatial sample.
        summary_variables = [
            name for name in SUMMARY_VARIABLES if name in derived.variables
        ]
        accumulators: dict[str, dict[str, Any]] = {
            name: {
                "count": 0,
                "sum": 0.0,
                "minimum": np.inf,
                "maximum": -np.inf,
                "median_sample": [],
            }
            for name in summary_variables
        }

        latitude_var = navigation.variables["latitude"]
        longitude_var = navigation.variables["longitude"]

        for start in range(0, n_scans, chunk_scans):
            end = min(start + chunk_scans, n_scans)
            print(f"    scans {start:,}–{end:,} / {n_scans:,}")

            # Navigation is read once per chunk and reused for coral/algae/sand.
            latitude = _read_float_block(latitude_var, start, end)
            longitude = _read_float_block(longitude_var, start, end)

            # Keep a globally aligned sampling grid across chunks.
            global_scan_indices = np.arange(start, end)
            selected_local_rows = np.flatnonzero(global_scan_indices % spatial_step == 0)

            class_values: dict[str, np.ndarray] = {}
            class_valid_masks: dict[str, np.ndarray] = {}

            for variable_name in summary_variables:
                variable = derived.variables[variable_name]
                values = _read_float_block(variable, start, end)

                valid = np.isfinite(values)
                accumulator = accumulators[variable_name]

                if variable_name in QUALITY_CLASS_VARIABLES:
                    class_values[variable_name] = values
                    class_valid_masks[variable_name] = valid
                    quality_counts[variable_name] += int(valid.sum())

                if valid.any():
                    valid_values = values[valid]
                    accumulator["count"] += int(valid_values.size)
                    accumulator["sum"] += float(valid_values.sum(dtype=np.float64))
                    accumulator["minimum"] = min(accumulator["minimum"], float(valid_values.min()))
                    accumulator["maximum"] = max(accumulator["maximum"], float(valid_values.max()))

                # Keep a bounded regular sample for median and spatial export.
                if selected_local_rows.size:
                    sampled_values = values[selected_local_rows, ::spatial_step]
                    sampled_valid = np.isfinite(sampled_values)
                    if sampled_valid.any():
                        sample_flat = sampled_values[sampled_valid]
                        remaining = max_spatial_rows - sum(
                            len(part) for part in accumulator["median_sample"]
                        )
                        if remaining > 0:
                            accumulator["median_sample"].append(sample_flat[:remaining].copy())

                    if variable_name in SPATIAL_VARIABLES:
                        sampled_lat = latitude[selected_local_rows, ::spatial_step]
                        sampled_lon = longitude[selected_local_rows, ::spatial_step]
                        spatial_valid = (
                            np.isfinite(sampled_values)
                            & np.isfinite(sampled_lat)
                            & np.isfinite(sampled_lon)
                            & (sampled_lat >= -90)
                            & (sampled_lat <= 90)
                            & (sampled_lon >= -180)
                            & (sampled_lon <= 180)
                        )
                        if spatial_valid.any():
                            units = safe_attr(_attribute(variable, "units", ""))
                            spatial_parts.append(
                                pd.DataFrame(
                                    {
                                        "latitude": sampled_lat[spatial_valid],
                                        "longitude": sampled_lon[spatial_valid],
                                        "value": sampled_values[spatial_valid],
                                        "source_file": path.name,
                                        "region": region_name,
                                        "observation_date": observation_date,
                                        "variable": variable_name,
                                        "units": units,
                                        "sampled_for_size": True,
                                    }
                                )
                            )

            # Assess class-mask consistency and geolocation for all pixels in this chunk.
            if all(name in class_values for name in QUALITY_CLASS_VARIABLES):
                common_class_valid = np.logical_and.reduce(
                    [class_valid_masks[name] for name in QUALITY_CLASS_VARIABLES]
                )
                valid_benthic_pixels += int(common_class_valid.sum())

                coordinate_valid = (
                    np.isfinite(latitude)
                    & np.isfinite(longitude)
                    & (latitude >= -90)
                    & (latitude <= 90)
                    & (longitude >= -180)
                    & (longitude <= 180)
                )
                valid_geolocation_pixels += int(coordinate_valid.sum())
                valid_benthic_geolocation_pixels += int(
                    (common_class_valid & coordinate_valid).sum()
                )

                probability_sum = (
                    class_values["coral"].astype(np.float64)
                    + class_values["algae"].astype(np.float64)
                    + class_values["sand"].astype(np.float64)
                )
                valid_probability_sums = probability_sum[common_class_valid]
                if valid_probability_sums.size:
                    probability_sum_count += int(valid_probability_sums.size)
                    probability_sum_total += float(valid_probability_sums.sum(dtype=np.float64))
                    probability_sum_min = min(
                        probability_sum_min, float(valid_probability_sums.min())
                    )
                    probability_sum_max = max(
                        probability_sum_max, float(valid_probability_sums.max())
                    )
                    probability_sum_in_range_count += int(
                        ((valid_probability_sums >= 0.95)
                         & (valid_probability_sums <= 1.05)).sum()
                    )

                # Export a small geospatial sample of BOTH valid and masked pixels.
                # This allows the dashboard to show where data are available.
                if selected_local_rows.size:
                    sampled_lat = latitude[selected_local_rows, ::spatial_step]
                    sampled_lon = longitude[selected_local_rows, ::spatial_step]
                    sampled_coord_valid = (
                        np.isfinite(sampled_lat)
                        & np.isfinite(sampled_lon)
                        & (sampled_lat >= -90)
                        & (sampled_lat <= 90)
                        & (sampled_lon >= -180)
                        & (sampled_lon <= 180)
                    )
                    sampled_benthic_valid = common_class_valid[
                        selected_local_rows, ::spatial_step
                    ]
                    sampled_coral = class_values["coral"][
                        selected_local_rows, ::spatial_step
                    ]
                    sampled_algae = class_values["algae"][
                        selected_local_rows, ::spatial_step
                    ]
                    sampled_sand = class_values["sand"][
                        selected_local_rows, ::spatial_step
                    ]
                    sampled_probability_sum = (
                        sampled_coral.astype(np.float64)
                        + sampled_algae.astype(np.float64)
                        + sampled_sand.astype(np.float64)
                    )

                    if sampled_coord_valid.any():
                        spatial_quality_sample_points += int(sampled_coord_valid.sum())
                        selected_valid = sampled_benthic_valid[sampled_coord_valid]
                        quality_frame = pd.DataFrame(
                            {
                                "latitude": sampled_lat[sampled_coord_valid],
                                "longitude": sampled_lon[sampled_coord_valid],
                                "source_file": path.name,
                                "flight_line": flight_line,
                                "region": region_name,
                                "observation_date": observation_date,
                                "is_benthic_valid": selected_valid,
                                "quality_status": np.where(
                                    selected_valid, "valid", "masked_or_invalid"
                                ),
                                "coral_probability": sampled_coral[sampled_coord_valid],
                                "algae_probability": sampled_algae[sampled_coord_valid],
                                "sand_probability": sampled_sand[sampled_coord_valid],
                                "probability_sum": sampled_probability_sum[sampled_coord_valid],
                                "sampled_for_size": True,
                            }
                        )
                        # Masked/invalid class values are not meaningful; export them as NaN.
                        for column in (
                            "coral_probability", "algae_probability", "sand_probability",
                            "probability_sum",
                        ):
                            quality_frame.loc[~quality_frame["is_benthic_valid"], column] = np.nan
                        spatial_quality_parts.append(quality_frame[SPATIAL_QUALITY_COLUMNS])

        # Attach full-scene pixel-quality metrics to the flight catalog.
        catalog_row.update(
            {
                "total_pixels": total_pixels,
                "valid_coral_pixels": quality_counts["coral"],
                "valid_algae_pixels": quality_counts["algae"],
                "valid_sand_pixels": quality_counts["sand"],
                "valid_benthic_pixels": valid_benthic_pixels,
                "masked_or_invalid_benthic_pixels": total_pixels - valid_benthic_pixels,
                "valid_benthic_pixel_pct": (
                    valid_benthic_pixels / total_pixels * 100 if total_pixels else np.nan
                ),
                "masked_or_invalid_benthic_pixel_pct": (
                    (total_pixels - valid_benthic_pixels) / total_pixels * 100
                    if total_pixels else np.nan
                ),
                "valid_geolocation_pixels": valid_geolocation_pixels,
                "valid_benthic_geolocation_pixels": valid_benthic_geolocation_pixels,
                "valid_benthic_geolocation_pct": (
                    valid_benthic_geolocation_pixels / total_pixels * 100
                    if total_pixels else np.nan
                ),
                "spatial_quality_sample_points": spatial_quality_sample_points,
                "spatial_sample_step": spatial_step,
                "probability_sum_mean": (
                    probability_sum_total / probability_sum_count
                    if probability_sum_count else np.nan
                ),
                "probability_sum_min": (
                    probability_sum_min if probability_sum_count else np.nan
                ),
                "probability_sum_max": (
                    probability_sum_max if probability_sum_count else np.nan
                ),
                "probability_sum_0_95_1_05_pct": (
                    probability_sum_in_range_count / probability_sum_count * 100
                    if probability_sum_count else np.nan
                ),
            }
        )

        for variable_name, accumulator in accumulators.items():
            variable = derived.variables[variable_name]
            sample_parts = accumulator["median_sample"]
            median_sample = (
                float(np.median(np.concatenate(sample_parts)))
                if sample_parts
                else np.nan
            )
            count = int(accumulator["count"])
            minimum = float(accumulator["minimum"]) if count else np.nan
            maximum = float(accumulator["maximum"]) if count else np.nan
            mean = _mean_from_sums(float(accumulator["sum"]), count)
            units = safe_attr(_attribute(variable, "units", ""))

            summary_rows.append(
                {
                    "source_file": path.name,
                    "flight_line": flight_line,
                    "region": region_name,
                    "observation_date": observation_date,
                    "variable": variable_name,
                    "long_name": safe_attr(_attribute(variable, "long_name", "")),
                    "units": units,
                    "dimensions": ",".join(variable.dimensions),
                    "valid_count": count,
                    "minimum": minimum,
                    "mean": mean,
                    "median_sampled": median_sample,
                    "maximum": maximum,
                    "median_sample_count": sum(len(part) for part in sample_parts),
                    "statistics_scope": "all valid pixels; median estimated from regular sample",
                }
            )

    return (
        catalog_row,
        inventory_row,
        variable_rows,
        summary_rows,
        spatial_parts,
        spatial_quality_parts,
    )


def process_nasa_files() -> pd.DataFrame:
    """Process all NASA .nc/.nc4/.cdf files and write dashboard-ready outputs."""
    directories = ensure_directories()
    raw_dir = directories["nasa_raw"]
    processed_dir = directories["processed"]

    extensions = {".nc", ".nc4", ".cdf"}
    netcdf_files = sorted(
        path for path in raw_dir.iterdir()
        if path.is_file() and path.suffix.lower() in extensions
    )

    if not netcdf_files:
        raise FileNotFoundError(
            f"Nenhum NetCDF NASA foi encontrado em {raw_dir}. "
            "Coloque os arquivos L2/RBEN nessa pasta."
        )

    region_name = str(getattr(settings, "REGION_NAME", "Great Barrier Reef"))
    chunk_scans = max(1, int(getattr(settings, "NASA_CHUNK_SCANS", 256)))
    max_spatial_rows = max(
        100,
        int(getattr(settings, "MAX_SPATIAL_ROWS_PER_VARIABLE", 20000)),
    )

    catalog_rows: list[dict[str, Any]] = []
    inventory_rows: list[dict[str, Any]] = []
    variable_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    spatial_parts: list[pd.DataFrame] = []
    spatial_quality_parts: list[pd.DataFrame] = []

    for index, path in enumerate(netcdf_files, start=1):
        print(f"\n[NASA {index}/{len(netcdf_files)}] Processando {path.name}")
        result = _process_one_file(
            path=path,
            region_name=region_name,
            chunk_scans=chunk_scans,
            max_spatial_rows=max_spatial_rows,
        )
        (
            catalog_row,
            inventory_row,
            file_variable_rows,
            file_summary_rows,
            file_spatial_parts,
            file_spatial_quality_parts,
        ) = result
        catalog_rows.append(catalog_row)
        inventory_rows.append(inventory_row)
        variable_rows.extend(file_variable_rows)
        summary_rows.extend(file_summary_rows)
        spatial_parts.extend(file_spatial_parts)
        spatial_quality_parts.extend(file_spatial_quality_parts)

    flight_catalog = pd.DataFrame(catalog_rows)
    flight_inventory = pd.DataFrame(inventory_rows)
    variable_inventory = pd.DataFrame(variable_rows)
    benthic_summary = pd.DataFrame(summary_rows)
    spatial_observations = (
        pd.concat(spatial_parts, ignore_index=True)
        if spatial_parts
        else pd.DataFrame(columns=SPATIAL_COLUMNS)
    )
    class_legend = pd.DataFrame(LEGEND_ROWS)
    spatial_validity_sample = (
        pd.concat(spatial_quality_parts, ignore_index=True)
        if spatial_quality_parts
        else pd.DataFrame(columns=SPATIAL_QUALITY_COLUMNS)
    )
    nasa_pixel_quality = flight_catalog[
        [
            "source_file",
            "flight_line",
            "region",
            "observation_date",
            "total_pixels",
            "valid_coral_pixels",
            "valid_algae_pixels",
            "valid_sand_pixels",
            "valid_benthic_pixels",
            "masked_or_invalid_benthic_pixels",
            "valid_benthic_pixel_pct",
            "masked_or_invalid_benthic_pixel_pct",
            "valid_geolocation_pixels",
            "valid_benthic_geolocation_pixels",
            "valid_benthic_geolocation_pct",
            "spatial_quality_sample_points",
            "spatial_sample_step",
            "probability_sum_mean",
            "probability_sum_min",
            "probability_sum_max",
            "probability_sum_0_95_1_05_pct",
        ]
    ].copy()

    # Summarize the sampled spatial mask separately from full-resolution counts.
    # These counts describe the map sample only, not all pixels in the NetCDF.
    if not spatial_validity_sample.empty:
        spatial_sample_summary = (
            spatial_validity_sample.groupby("source_file", as_index=False)
            .agg(
                spatial_sample_points=("is_benthic_valid", "size"),
                spatial_sample_valid_points=("is_benthic_valid", "sum"),
            )
        )
        spatial_sample_summary["spatial_sample_masked_points"] = (
            spatial_sample_summary["spatial_sample_points"]
            - spatial_sample_summary["spatial_sample_valid_points"]
        )
        spatial_sample_summary["spatial_sample_valid_pct"] = (
            spatial_sample_summary["spatial_sample_valid_points"]
            / spatial_sample_summary["spatial_sample_points"] * 100
        )
        nasa_pixel_quality = nasa_pixel_quality.merge(
            spatial_sample_summary, on="source_file", how="left"
        )

    outputs = {
        "flight_catalog.csv": flight_catalog,
        "flight_inventory.csv": flight_inventory,
        "variable_inventory.csv": variable_inventory,
        "benthic_variable_summary.csv": benthic_summary,
        "spatial_observations.csv": spatial_observations,
        "spatial_validity_sample.csv": spatial_validity_sample,
        "nasa_pixel_quality.csv": nasa_pixel_quality,
        "class_legend.csv": class_legend,
    }

    for filename, frame in outputs.items():
        frame.to_csv(processed_dir / filename, index=False)
        print(f"[NASA] Salvo: {processed_dir / filename} ({len(frame):,} linhas)")

    config = {
        "project": "CoralWatch",
        "source": "NASA CORAL / PRISM Benthic Cover L2/RBEN",
        "doi": "10.5067/PRISM/CORAL/L2/RBEN/V1",
        "source_url": "https://oceandata.sci.gsfc.nasa.gov/coral_browser/",
        "region_selected": region_name,
        "historical_data_note": (
            "CORAL campaign observations are historical (2016-2017); "
            "do not present them as current or real-time reef health."
        ),
        "probability_note": (
            "coral, algae and sand are per-pixel class probabilities from 0 to 1; "
            "they are not direct diagnoses of coral health or mortality."
        ),
        "statistics_note": (
            "Counts, minimum, mean and maximum use all valid pixels. "
            "Median is estimated from a regular spatial sample."
        ),
        "quality_note": (
            "A benthic pixel is valid when coral, algae and sand are all finite "
            "and within their declared valid ranges. Masked/invalid pixels are "
            "data-availability gaps, not evidence of ecological degradation."
        ),
        "spatial_validity_note": (
            "spatial_validity_sample.csv is a regular geospatial sample of "
            "coordinates with valid navigation values. It includes both valid "
            "and masked/invalid benthic classifications to visualize data coverage."
        ),
        "files_processed": [path.name for path in netcdf_files],
        "spatial_sample_limit_per_variable_per_flight": max_spatial_rows,
        "chunk_scans": chunk_scans,
        "outputs": list(outputs.keys()) + ["dashboard_config.json"],
    }
    (processed_dir / "dashboard_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n[NASA] Processamento concluído.")
    print(f"[NASA] Arquivos processados: {len(netcdf_files)}")
    print(f"[NASA] Variáveis catalogadas: {len(variable_inventory)}")
    print(f"[NASA] Linhas de resumo: {len(benthic_summary)}")
    print(f"[NASA] Pontos espaciais exportados: {len(spatial_observations):,}")
    print(f"[NASA] Pontos da amostra de qualidade: {len(spatial_validity_sample):,}")
    print(f"[NASA] Saídas em: {processed_dir}")

    return flight_catalog


if __name__ == "__main__":
    process_nasa_files()
