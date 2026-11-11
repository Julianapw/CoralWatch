
"""
CoralWatch - NOAA NetCDF processing.

Outputs:
- noaa_daily_summary.csv
- noaa_spatial_summary.csv
- noaa_latest_map.csv
- noaa_alert_summary.csv
- noaa_config.json
- noaa_sst_history_daily.csv
"""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from netCDF4 import Dataset, num2date


# ============================================================
# 1. PROJECT PATHS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]

INPUT_DIR = PROJECT_DIR / "data" / "raw" / "noaa"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. VARIABLES TO ANALYZE
# ============================================================

CONTINUOUS_VARIABLES = [
    "CRW_SST",
    "CRW_SSTANOMALY",
    "CRW_HOTSPOT",
    "CRW_DHW",
]

BAA_VARIABLE = "CRW_BAA_7D_MAX"

BAA_LEVELS = {
    0: "no_stress",
    1: "bleaching_watch",
    2: "bleaching_warning",
    3: "alert_level_1",
    4: "alert_level_2",
}


# ============================================================
# 3. VALID DATA READING
# ============================================================

def read_valid_values(variable):
    """
    Convert masked, fill and out-of-range values to NaN.
    """

    values = (
        np.ma.asarray(variable[:])
        .astype(float)
        .filled(np.nan)
    )

    valid_min = getattr(variable, "valid_min", None)
    valid_max = getattr(variable, "valid_max", None)
    missing_value = getattr(variable, "missing_value", None)
    fill_value = getattr(variable, "_FillValue", None)

    if valid_min is not None:
        values[values < float(valid_min)] = np.nan

    if valid_max is not None:
        values[values > float(valid_max)] = np.nan

    for marker in (missing_value, fill_value):
        if marker is not None:
            values[values == float(marker)] = np.nan

    return values


# ============================================================
# 4. STATISTICAL HELPER FUNCTIONS
# ============================================================

def calculate_statistics(values):
    """
    Calculate basic statistics while ignoring NaN values.
    """

    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]

    if valid.size == 0:
        return {
            "mean": np.nan,
            "min": np.nan,
            "max": np.nan,
            "valid_count": 0,
        }

    return {
        "mean": float(np.mean(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "valid_count": int(valid.size),
    }


def add_baa_statistics(row, values):
    """
    Add the distribution of NOAA Bleaching Alert Area levels.
    """

    valid = np.asarray(values, dtype=float)
    valid = valid[np.isfinite(valid)]

    if valid.size == 0:
        row["BAA_max"] = np.nan

        for level, name in BAA_LEVELS.items():
            row[f"BAA_{name}_count"] = 0
            row[f"BAA_{name}_percentage"] = np.nan

        return row

    row["BAA_max"] = int(np.max(valid))

    for level, name in BAA_LEVELS.items():
        count = int(np.sum(valid == level))

        row[f"BAA_{name}_count"] = count
        row[f"BAA_{name}_percentage"] = (
            count / valid.size * 100
        )

    return row


# ============================================================
# 5. DATE AND COORDINATE HELPERS
# ============================================================

def get_dates(dataset):
    """Read and convert NetCDF time coordinates."""

    time_variable = dataset.variables["time"]

    values = num2date(
        time_variable[:],
        units=time_variable.units,
        calendar=getattr(
            time_variable,
            "calendar",
            "standard",
        ),
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=True,
    )

    return [
        pd.Timestamp(value).strftime("%Y-%m-%d")
        for value in values
    ]


def get_grid(dataset, shape):
    """
    Return latitude and longitude arrays matching a 2-D spatial field.
    """

    lat_name = (
        "latitude"
        if "latitude" in dataset.variables
        else "lat"
    )

    lon_name = (
        "longitude"
        if "longitude" in dataset.variables
        else "lon"
    )

    if (
        lat_name not in dataset.variables
        or lon_name not in dataset.variables
    ):
        raise ValueError(
            "Latitude/longitude coordinates are missing."
        )

    latitude = np.asarray(
        dataset.variables[lat_name][:],
        dtype=float,
    )

    longitude = np.asarray(
        dataset.variables[lon_name][:],
        dtype=float,
    )

    if latitude.ndim == 1 and longitude.ndim == 1:
        lon_grid, lat_grid = np.meshgrid(
            longitude,
            latitude,
        )

    elif latitude.shape == longitude.shape:
        lat_grid = latitude
        lon_grid = longitude

    else:
        raise ValueError(
            "Unsupported latitude/longitude coordinate dimensions."
        )

    if (
        lat_grid.shape != shape
        or lon_grid.shape != shape
    ):
        raise ValueError(
            f"Coordinate shape {lat_grid.shape} "
            f"does not match data shape {shape}."
        )

    return lat_grid, lon_grid


def get_time_slice(values, index, time_count):
    """Extract one two-dimensional spatial field from a variable."""

    if values is None:
        return None

    if values.ndim == 3:
        return values[index]

    if values.ndim == 2 and time_count == 1:
        return values

    raise ValueError(
        f"Unexpected NOAA variable dimensions: {values.shape}"
    )


def region_from_filename(path):
    """
    Extract the NOAA geographic footprint identifier
    from the original NetCDF filename.
    """

    return path.name.split("_NOAA_", 1)[0]


# ============================================================
# 6. RECENT NOAA FILE ANALYSIS
# ============================================================

def analyze_recent_file(path):
    """
    Summarize every date and export the pixel map
    for the latest available observation date.
    """

    daily_rows = []
    map_rows = []

    spatial_row = {
        "region": region_from_filename(path)
    }

    with Dataset(path, mode="r") as dataset:

        # ----------------------------------------------------
        # 6.1 DATE INFORMATION
        # ----------------------------------------------------

        dates = get_dates(dataset)
        time_count = len(dates)

        if time_count == 0:
            raise ValueError(
                f"No time observations found in {path.name}."
            )

        # ----------------------------------------------------
        # 6.2 READ NOAA VARIABLES
        # ----------------------------------------------------

        arrays = {}

        for variable_name in (
            CONTINUOUS_VARIABLES + [BAA_VARIABLE]
        ):

            if variable_name in dataset.variables:
                arrays[variable_name] = read_valid_values(
                    dataset.variables[variable_name]
                )

        if not arrays:
            raise ValueError(
                f"No expected NOAA variables found in {path.name}."
            )

        # ----------------------------------------------------
        # 6.3 SPATIAL SUMMARY
        # ----------------------------------------------------

        for variable_name in CONTINUOUS_VARIABLES:

            if variable_name not in arrays:
                continue

            prefix = variable_name.replace("CRW_", "")

            stats = calculate_statistics(
                arrays[variable_name].ravel()
            )

            spatial_row[f"{prefix}_mean"] = stats["mean"]
            spatial_row[f"{prefix}_min"] = stats["min"]
            spatial_row[f"{prefix}_max"] = stats["max"]

            spatial_row[f"{prefix}_valid_count"] = (
                stats["valid_count"]
            )

        if BAA_VARIABLE in arrays:
            spatial_row = add_baa_statistics(
                spatial_row,
                arrays[BAA_VARIABLE].ravel(),
            )

        spatial_row["number_of_days"] = time_count

        # ----------------------------------------------------
        # 6.4 DAILY TIME SERIES
        # ----------------------------------------------------

        for index, observed_date in enumerate(dates):

            row = {
                "region": spatial_row["region"],
                "date": observed_date,
            }

            for variable_name in CONTINUOUS_VARIABLES:

                if variable_name not in arrays:
                    continue

                prefix = variable_name.replace("CRW_", "")

                daily_values = get_time_slice(
                    arrays[variable_name],
                    index,
                    time_count,
                )

                stats = calculate_statistics(
                    daily_values
                )

                row[f"{prefix}_mean"] = stats["mean"]
                row[f"{prefix}_min"] = stats["min"]
                row[f"{prefix}_max"] = stats["max"]

                row[f"{prefix}_valid_count"] = (
                    stats["valid_count"]
                )

            if BAA_VARIABLE in arrays:

                baa_values = get_time_slice(
                    arrays[BAA_VARIABLE],
                    index,
                    time_count,
                )

                row = add_baa_statistics(
                    row,
                    baa_values,
                )

            daily_rows.append(row)

        # ----------------------------------------------------
        # 6.5 FIND THE LATEST OBSERVATION DATE
        # ----------------------------------------------------

        latest_index = max(
            range(time_count),
            key=lambda index: dates[index],
        )

        latest_date = dates[latest_index]

        # ----------------------------------------------------
        # 6.6 BUILD THE LATEST PIXEL MAP
        # ----------------------------------------------------

        reference_array = next(iter(arrays.values()))

        latest_field = get_time_slice(
            reference_array,
            latest_index,
            time_count,
        )

        lat_grid, lon_grid = get_grid(
            dataset,
            latest_field.shape,
        )

        # Geographic bounds are added to the spatial summary.
        # These bounds can be used to create approximate centroids
        # when a pixel-level map is unavailable.

        valid_latitudes = lat_grid[
            np.isfinite(lat_grid)
            & (lat_grid >= -90)
            & (lat_grid <= 90)
        ]

        valid_longitudes = lon_grid[
            np.isfinite(lon_grid)
            & (lon_grid >= -180)
            & (lon_grid <= 180)
        ]

        if valid_latitudes.size > 0:
            spatial_row["latitude_min"] = float(
                np.min(valid_latitudes)
            )

            spatial_row["latitude_max"] = float(
                np.max(valid_latitudes)
            )

        if valid_longitudes.size > 0:
            spatial_row["longitude_min"] = float(
                np.min(valid_longitudes)
            )

            spatial_row["longitude_max"] = float(
                np.max(valid_longitudes)
            )

        # Extract every available variable for the latest date.

        latest_fields = {}

        for variable_name, values in arrays.items():

            latest_fields[variable_name] = get_time_slice(
                values,
                latest_index,
                time_count,
            )

        flat_lat = lat_grid.ravel()
        flat_lon = lon_grid.ravel()

        flattened = {
            name: values.ravel()
            for name, values in latest_fields.items()
        }

        # Create one CSV row per valid geographic pixel.

        for pixel_index in range(flat_lat.size):

            latitude = float(flat_lat[pixel_index])
            longitude = float(flat_lon[pixel_index])

            row = {
                "region": spatial_row["region"],
                "date": latest_date,
                "latitude": latitude,
                "longitude": longitude,
            }

            for name, values in flattened.items():

                row[name] = float(
                    values[pixel_index]
                )

            has_measurement = any(
                np.isfinite(row.get(name, np.nan))
                for name in arrays
            )

            valid_coordinates = (
                np.isfinite(latitude)
                and np.isfinite(longitude)
                and -90 <= latitude <= 90
                and -180 <= longitude <= 180
            )

            if has_measurement and valid_coordinates:
                map_rows.append(row)

    return daily_rows, spatial_row, map_rows


# ============================================================
# 7. HISTORICAL SST ANALYSIS
# ============================================================

def analyze_history_file(path):
    """
    Create one regional daily SST mean per date
    from a historical NOAA NetCDF chunk.
    """

    rows = []

    region = region_from_filename(path)

    with Dataset(path, mode="r") as dataset:

        if "CRW_SST" not in dataset.variables:
            raise ValueError(
                f"CRW_SST not found in {path.name}."
            )

        dates = get_dates(dataset)

        values = read_valid_values(
            dataset.variables["CRW_SST"]
        )

        for index, observed_date in enumerate(dates):

            daily_values = get_time_slice(
                values,
                index,
                len(dates),
            )

            stats = calculate_statistics(
                daily_values
            )

            rows.append({
                "region": region,
                "date": observed_date,
                "SST_mean": stats["mean"],
                "SST_min": stats["min"],
                "SST_max": stats["max"],
                "SST_valid_count": stats["valid_count"],
            })

    return rows


# ============================================================
# 8. SAVE RECENT NOAA OUTPUTS
# ============================================================

def write_recent_outputs(files):

    daily_rows = []
    spatial_rows = []
    map_rows = []

    for path in files:

        print(
            f"Processing recent NOAA file: {path.name}"
        )

        daily, spatial, pixels = analyze_recent_file(path)

        daily_rows.extend(daily)
        spatial_rows.append(spatial)
        map_rows.extend(pixels)

    if not daily_rows:
        print("No recent NOAA records found.")
        return

    # --------------------------------------------------------
    # 8.1 DAILY SUMMARY
    # --------------------------------------------------------

    daily_df = pd.DataFrame(daily_rows)

    daily_df["date"] = pd.to_datetime(
        daily_df["date"]
    )

    daily_df = (
        daily_df
        .sort_values(["region", "date"])
        .drop_duplicates(
            ["region", "date"],
            keep="last",
        )
    )

    # --------------------------------------------------------
    # 8.2 SPATIAL SUMMARY
    # --------------------------------------------------------

    spatial_df = (
        pd.DataFrame(spatial_rows)
        .drop_duplicates("region", keep="last")
    )

    # --------------------------------------------------------
    # 8.3 LATEST PIXEL MAP
    # --------------------------------------------------------

    map_df = pd.DataFrame(map_rows)

    if not map_df.empty:

        map_df["date"] = pd.to_datetime(
            map_df["date"]
        )

        latest_dates = (
            map_df.groupby("region")["date"]
            .transform("max")
        )

        map_df = map_df[
            map_df["date"] == latest_dates
        ]

        map_df = map_df.drop_duplicates(
            [
                "region",
                "date",
                "latitude",
                "longitude",
            ],
            keep="last",
        )

    # --------------------------------------------------------
    # 8.4 SAVE CSV FILES
    # --------------------------------------------------------

    daily_df.to_csv(
        OUTPUT_DIR / "noaa_daily_summary.csv",
        index=False,
        encoding="utf-8",
    )

    spatial_df.to_csv(
        OUTPUT_DIR / "noaa_spatial_summary.csv",
        index=False,
        encoding="utf-8",
    )

    map_df.to_csv(
        OUTPUT_DIR / "noaa_latest_map.csv",
        index=False,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 8.5 ALERT SUMMARY
    # --------------------------------------------------------

    alert_rows = []

    if (
        not map_df.empty
        and "CRW_BAA_7D_MAX" in map_df
    ):

        for region, group in map_df.groupby("region"):

            valid = pd.to_numeric(
                group["CRW_BAA_7D_MAX"],
                errors="coerce",
            ).dropna()

            valid = valid[
                valid.isin(list(BAA_LEVELS))
            ]

            for level, alert_name in BAA_LEVELS.items():

                count = int(
                    (valid == level).sum()
                )

                alert_rows.append({
                    "region": region,
                    "date": group["date"].max().strftime(
                        "%Y-%m-%d"
                    ),
                    "baa_level": level,
                    "alert_label": alert_name,
                    "pixel_count": count,
                    "pixel_percent": (
                        count / len(valid) * 100
                        if len(valid)
                        else np.nan
                    ),
                })

    pd.DataFrame(alert_rows).to_csv(
        OUTPUT_DIR / "noaa_alert_summary.csv",
        index=False,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # 8.6 NOAA CONFIGURATION
    # --------------------------------------------------------

    config = {
        "source": "NOAA Coral Reef Watch v3.1",
        "product": (
            "Daily global 5-km satellite coral bleaching "
            "heat stress products"
        ),
        "latest_date_by_region": {
            region: date.strftime("%Y-%m-%d")
            for region, date in (
                daily_df.groupby("region")["date"].max().items()
            )
        },
        "latest_map_file": "noaa_latest_map.csv",
        "note": (
            "NOAA pixels represent ocean grid cells in the selected "
            "geographic footprints. They are not individual coral colonies."
        ),
    }

    config_path = OUTPUT_DIR / "noaa_config.json"

    config_path.write_text(
        json.dumps(
            config,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Recent NOAA outputs created.")


# ============================================================
# 9. SAVE HISTORICAL SST OUTPUT
# ============================================================

def write_history_output(files):

    history_rows = []

    for path in files:

        print(
            f"Processing historical SST file: {path.name}"
        )

        try:
            history_rows.extend(
                analyze_history_file(path)
            )

        except Exception as exc:
            print(
                f"Could not process {path.name}: {exc}"
            )

    if not history_rows:
        print(
            "No historical SST records found. "
            "Existing history CSV was not changed."
        )
        return

    history_df = pd.DataFrame(history_rows)

    history_df["date"] = pd.to_datetime(
        history_df["date"]
    )

    history_df = (
        history_df
        .sort_values(["region", "date"])
        .drop_duplicates(
            ["region", "date"],
            keep="last",
        )
    )

    history_df.to_csv(
        OUTPUT_DIR / "noaa_sst_history_daily.csv",
        index=False,
        encoding="utf-8",
    )

    print(
        "Historical SST output created: "
        f"{len(history_df):,} daily regional records."
    )


# ============================================================
# 10. PROCESS RECENT NOAA FILES
# ============================================================

def analyze_recent_files(files=None):

    if files is None:
        files = sorted(
            INPUT_DIR.glob("*_NOAA_last_*_days.nc")
        )

    files = [
        Path(path)
        for path in files
        if Path(path).exists()
    ]

    if files:
        write_recent_outputs(files)

    else:
        print("No recent NOAA NetCDF files found.")


# ============================================================
# 11. PROCESS HISTORICAL NOAA FILES
# ============================================================

def analyze_history_files(files=None):

    if files is None:
        files = sorted(
            INPUT_DIR.glob("*_NOAA_SST_history_*.nc")
        )

    files = [
        Path(path)
        for path in files
        if Path(path).exists()
    ]

    if files:
        write_history_output(files)

    else:
        print("No historical SST NetCDF files found.")


# ============================================================
# 12. RUN ALL ANALYSES
# ============================================================

def run_analysis():

    analyze_recent_files()
    analyze_history_files()


def main():

    run_analysis()


if __name__ == "__main__":
    main()
