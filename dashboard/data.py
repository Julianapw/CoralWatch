
"""Schema adaptation without importing or running the scientific pipeline."""

from pathlib import Path
import json

import numpy as np
import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"

FILES = (
    "flight_catalog.csv",
    "benthic_variable_summary.csv",
    "spatial_observations.csv",
    "variable_inventory.csv",
    "class_legend.csv",
    "dashboard_config.json",
    "nasa_pixel_quality.csv",
    "noaa_thermal_timeseries.csv",
    "noaa_latest_map.csv",
    "noaa_alert_summary.csv",
    "noaa_config.json",
    "noaa_daily_summary.csv",
    "noaa_spatial_summary.csv",
    "integrated_regional_summary.csv",
    "noaa_sst_history_daily.csv",
)

ALIASES = {
    "sst_mean": ("SST_mean", "sst_c_mean"),
    "anomaly_mean": ("SSTANOMALY_mean", "sst_anomaly_c_mean"),
    "hotspot_mean": ("HOTSPOT_mean", "hotspot_c_mean"),
    "hotspot_max": ("HOTSPOT_max", "hotspot_c_max"),
    "dhw_mean": ("DHW_mean", "dhw_celsius_weeks_mean"),
    "dhw_max": ("DHW_max", "dhw_celsius_weeks_max"),
    "baa": ("BAA_max", "baa_7d_max", "CRW_BAA_7D_MAX"),
    "sst": ("sst_c", "CRW_SST"),
    "hotspot": ("hotspot_c", "CRW_HOTSPOT"),
    "dhw": ("dhw_celsius_weeks", "CRW_DHW"),
}


def signature(directory):
    """Build a cache fingerprint from file names, modification times and sizes."""
    directory = Path(directory)

    return tuple(
        (
            name,
            (directory / name).stat().st_mtime_ns,
            (directory / name).stat().st_size,
        )
        for name in FILES
        if (directory / name).exists()
    )


@st.cache_data(show_spinner=False)
def _read(directory, fingerprint):
    """Read processed CSV and JSON files without running the data pipeline."""
    frames = {}
    configs = {}
    messages = []

    for name in FILES:
        path = Path(directory) / name

        if not path.exists():
            continue

        try:
            if path.suffix == ".json":
                obj = json.loads(
                    path.read_text(encoding="utf-8-sig")
                )

                if not isinstance(obj, dict):
                    raise ValueError("Expected a JSON object.")

                configs[name] = obj

            else:
                frames[name] = pd.read_csv(path)

                if frames[name].empty:
                    messages.append(
                        f"{name}: file contains no observations."
                    )

        except (OSError, ValueError, pd.errors.ParserError) as exc:
            messages.append(
                f"{name}: could not be loaded ({exc})."
            )

    return frames, configs, messages


def numeric(series):
    """Convert values to numeric and mask common fill values."""
    result = pd.to_numeric(series, errors="coerce")

    invalid_values = [
        -999,
        -9999,
        -32767,
        -32768,
        32767,
        65535,
    ]

    return result.mask(
        ~np.isfinite(result)
        | result.isin(invalid_values)
    )


def apply_metadata(data, inventory, column):
    """Respect declared valid ranges and fill values for each variable/file."""
    data = data.copy()

    if column not in data:
        return data

    data[column] = numeric(data[column])

    if "variable" not in data or "variable" not in inventory:
        return data

    keys = ["variable"]

    if (
        "source_file" in data
        and "source_file" in inventory
    ):
        keys.append("source_file")

    metadata_fields = [
        ("valid_min", "min"),
        ("valid_max", "max"),
        ("_FillValue", "fill"),
        ("missing_value", "fill"),
    ]

    for _, metadata in inventory.iterrows():
        mask = pd.Series(True, index=data.index)

        for key in keys:
            mask &= data[key] == metadata[key]

        for field, operation in metadata_fields:
            value = pd.to_numeric(
                metadata.get(field),
                errors="coerce",
            )

            if pd.isna(value):
                continue

            if operation == "min":
                invalid = data[column] < value

            elif operation == "max":
                invalid = data[column] > value

            else:
                invalid = data[column] == value

            data.loc[mask & invalid, column] = np.nan

    return data


def dates(series):
    """Parse dates as timezone-naive timestamps in UTC."""
    return (
        pd.to_datetime(
            series,
            errors="coerce",
            utc=True,
            format="mixed",
        )
        .dt.tz_localize(None)
    )


def adapt_noaa(frame, regional=False):
    """
    Adapt NOAA source columns to a common dashboard schema.

    Regional datasets must contain a region identifier.
    Global legacy datasets receive a clearly labeled global identifier.
    """
    data = frame.copy()

    if "date" not in data:
        return pd.DataFrame()

    if regional and "region" not in data:
        return pd.DataFrame()

    data["date"] = dates(data["date"])
    data = data.dropna(subset=["date"])

    if regional:
        data = data.dropna(subset=["region"])
        data["region"] = data["region"].astype(str).str.strip()

    else:
        data["region"] = (
            "Global file footprint (no regional breakdown)"
        )

    for target, aliases in ALIASES.items():
        for source in aliases:
            if source in data:
                data[target] = numeric(data[source])
                break

    if "baa" in data:
        data["baa"] = data["baa"].where(
            (data["baa"] >= 0)
            & (data["baa"] % 1 == 0)
        )

    return data.drop_duplicates(
        ["region", "date"],
        keep="last",
    )


def latest_by_region(data):
    """Return the latest available observation for each region."""
    if data.empty or not {"region", "date"}.issubset(data.columns):
        return pd.DataFrame()

    return (
        data.sort_values("date")
        .groupby("region", as_index=False)
        .tail(1)
        .copy()
    )


def coordinates(frame):
    """Keep rows with valid geographic coordinates."""
    data = frame.copy()

    if not {"latitude", "longitude"}.issubset(data.columns):
        return pd.DataFrame()

    for column in ("latitude", "longitude"):
        data[column] = numeric(data[column])

    valid = (
        data["latitude"].between(-90, 90)
        & data["longitude"].between(-180, 180)
    )

    return data[valid].copy()


def load(directory=None):
    """
    Load all available processed datasets.

    NASA, recent NOAA and historical NOAA data are kept separate.
    The function does not download or process raw NetCDF files.
    """
    directory = (
        Path(directory)
        if directory is not None
        else DATA_DIR
    )

    raw, config, messages = _read(
        str(directory),
        signature(directory),
    )

    # ---------------------------------------------------------
    # NOAA RECENT DAILY DATA
    # ---------------------------------------------------------

    regional = adapt_noaa(
        raw.get(
            "noaa_daily_summary.csv",
            pd.DataFrame(),
        ),
        regional=True,
    )

    original = adapt_noaa(
        raw.get(
            "noaa_thermal_timeseries.csv",
            pd.DataFrame(),
        )
    )

    noaa, source = (
        (regional, "noaa_daily_summary.csv")
        if not regional.empty
        else (original, "noaa_thermal_timeseries.csv")
    )

    # ---------------------------------------------------------
    # NOAA HISTORICAL SST DATA
    # ---------------------------------------------------------

    history = adapt_noaa(
        raw.get(
            "noaa_sst_history_daily.csv",
            pd.DataFrame(),
        ),
        regional=True,
    )

    # ---------------------------------------------------------
    # INPUT VALIDATION
    # ---------------------------------------------------------

    required_columns = [
        (
            "noaa_daily_summary.csv",
            {"date", "region"},
        ),
        (
            "noaa_thermal_timeseries.csv",
            {"date"},
        ),
        (
            "noaa_sst_history_daily.csv",
            {"date", "region", "SST_mean"},
        ),
        (
            "benthic_variable_summary.csv",
            {"variable", "mean"},
        ),
    ]

    for name, required in required_columns:
        if name not in raw or raw[name].empty:
            continue

        missing = required - set(raw[name].columns)

        if missing:
            messages.append(
                f"{name}: required columns are missing: "
                f"{sorted(missing)}."
            )

        if (
            "date" in raw[name]
            and dates(raw[name]["date"]).isna().any()
        ):
            messages.append(
                f"{name}: invalid dates were excluded."
            )

    # ---------------------------------------------------------
    # NASA FLIGHT CATALOG
    # ---------------------------------------------------------

    catalog = raw.get(
        "flight_catalog.csv",
        pd.DataFrame(),
    ).copy()

    integrated = raw.get(
        "integrated_regional_summary.csv",
        pd.DataFrame(),
    )

    if catalog.empty and not integrated.empty:
        catalog = integrated.rename(
            columns={
                "nasa_region": "region",
                "nasa_observation_date": "observation_date",
            }
        ).copy()

        messages.append(
            "NASA catalog: using integrated_regional_summary.csv "
            "as a fallback. Historical NOAA statistics are not "
            "treated as current observations."
        )

    if "observation_date" in catalog:
        catalog["observation_date"] = dates(
            catalog["observation_date"]
        )

    # ---------------------------------------------------------
    # NASA BENTHIC SUMMARY
    # ---------------------------------------------------------

    benthic = raw.get(
        "benthic_variable_summary.csv",
        pd.DataFrame(),
    ).copy()

    if benthic.empty and not integrated.empty:
        parts = []

        for variable in ("coral", "algae", "sand"):
            column = variable + "_mean"

            if column in integrated:
                part = catalog.copy()
                part["variable"] = variable
                part["mean"] = numeric(
                    integrated[column]
                )
                parts.append(part)

        benthic = (
            pd.concat(parts, ignore_index=True)
            if parts
            else pd.DataFrame()
        )

    benthic = prepare_benthic(
        benthic,
        catalog,
        raw,
        config,
    )

    # ---------------------------------------------------------
    # NASA SPATIAL OBSERVATIONS
    # ---------------------------------------------------------

    spatial = raw.get(
        "spatial_observations.csv",
        pd.DataFrame(),
    ).copy()

    spatial = attach_catalog(
        spatial,
        catalog,
    )

    spatial = apply_metadata(
        spatial,
        raw.get(
            "variable_inventory.csv",
            pd.DataFrame(),
        ),
        "value",
    )

    if "observation_date" in spatial:
        spatial["observation_date"] = dates(
            spatial["observation_date"]
        )

    # ---------------------------------------------------------
    # NOAA LATEST PIXEL MAP
    # ---------------------------------------------------------

    pixels = coordinates(
        raw.get(
            "noaa_latest_map.csv",
            pd.DataFrame(),
        )
    )

    for target, aliases in ALIASES.items():
        for column in aliases:
            if column in pixels:
                pixels[target] = numeric(
                    pixels[column]
                )
                break

    if "date" in pixels:
        pixels["date"] = dates(pixels["date"])

        latest_date = pixels["date"].max()

        if pd.notna(latest_date):
            pixels = pixels[
                pixels["date"] == latest_date
            ].copy()

        else:
            messages.append(
                "noaa_latest_map.csv: no valid observation "
                "date was found. The recent pixel map is unavailable."
            )
            pixels = pixels.iloc[0:0]

    elif not pixels.empty:
        metadata = config.get(
            "noaa_config.json",
            {},
        )

        observed = metadata.get(
            "latest_date",
            metadata.get("latest_observation_date"),
        )

        pixels["date"] = dates(
            pd.Series(
                [observed] * len(pixels),
                index=pixels.index,
            )
        )

        if pixels["date"].isna().all():
            messages.append(
                "noaa_latest_map.csv: observation date is missing. "
                "The recent pixel map is unavailable."
            )
            pixels = pixels.iloc[0:0]

    if "baa" in pixels:
        pixels["baa"] = pixels["baa"].where(
            (pixels["baa"] >= 0)
            & (pixels["baa"] % 1 == 0)
        )

    # ---------------------------------------------------------
    # RETURN DATA BUNDLE
    # ---------------------------------------------------------

    return {
        "raw": raw,
        "config": config,
        "messages": messages,
        "catalog": catalog,
        "benthic": benthic,
        "spatial": spatial,
        "noaa": noaa,
        "history": history,
        "source": source,
        "regional": not regional.empty,
        "pixels": pixels,
    }


def attach_catalog(data, catalog):
    """Attach NASA flight metadata when an unambiguous key is available."""
    data = data.copy()

    for key in ("source_file", "flight_line"):
        if (
            key in data
            and key in catalog
            and not catalog[key].duplicated().any()
        ):
            extras = [
                column
                for column in (
                    "flight_line",
                    "region",
                    "observation_date",
                )
                if column in catalog and column not in data
            ]

            if extras:
                data = data.merge(
                    catalog[[key] + extras],
                    on=key,
                    how="left",
                    validate="many_to_one",
                )

            break

    return data


def prepare_benthic(data, catalog, raw, config):
    """
    Adapt benthic summary values using declared metadata.

    Percentages are assigned only when explicit evidence supports
    a percentage unit or a 0-1 probability scale.
    """
    if not {"variable", "mean"}.issubset(data.columns):
        return pd.DataFrame()

    data = attach_catalog(
        data,
        catalog,
    )

    data = data[
        data["variable"].isin(
            ["coral", "algae", "sand"]
        )
    ].copy()

    if "flight_line" not in data:
        return pd.DataFrame()

    legend = raw.get(
        "class_legend.csv",
        pd.DataFrame(),
    )

    inventory = raw.get(
        "variable_inventory.csv",
        pd.DataFrame(),
    )

    data = apply_metadata(
        data,
        inventory,
        "mean",
    )

    if "valid_count" in data:
        data.loc[
            numeric(data["valid_count"]) <= 0,
            "mean",
        ] = np.nan

    data["unit_label"] = "unit not confirmed"
    data["measure"] = numeric(data["mean"])

    probability_note = (
        config.get("dashboard_config.json", {})
        .get("probability_note", "")
    )

    for index, row in data.iterrows():
        unit = str(
            row.get("units", "")
        ).lower().strip()

        evidence = str(probability_note).lower()

        metadata = inventory

        if "variable" in metadata:
            metadata = metadata[
                metadata["variable"] == row["variable"]
            ]

            if (
                "source_file" in metadata
                and "source_file" in row
            ):
                metadata = metadata[
                    metadata["source_file"] == row["source_file"]
                ]

            if not unit or unit == "nan":
                unit = (
                    str(metadata.iloc[0].get("units", "")).lower()
                    if not metadata.empty
                    else ""
                )

        if "variable" in legend:
            legend_values = legend[
                legend["variable"] == row["variable"]
            ]

            evidence += " ".join(
                legend_values.astype(str).values.ravel()
            ).lower()

        if unit in ("%", "percent", "percentage"):
            data.loc[index, "unit_label"] = "% (declared measurement)"

            data.loc[index, "measure"] = numeric(
                pd.Series([row["mean"]])
            ).iloc[0]

        elif (
            "probabilit" in evidence
            and (
                "0 to 1" in evidence
                or "0–1" in evidence
            )
        ):
            data.loc[index, "unit_label"] = (
                "% mean class probability"
            )

            data.loc[index, "measure"] = (
                numeric(pd.Series([row["mean"]])).iloc[0] * 100
            )

        else:
            data.loc[index, "unit_label"] = (
                unit or "unit not confirmed"
            )

    percentage = data["unit_label"].str.startswith("%")

    data.loc[
        percentage & ~data["measure"].between(0, 100),
        "measure",
    ] = np.nan

    if "observation_date" in data:
        data["observation_date"] = dates(
            data["observation_date"]
        )

    # Ambiguous duplicate summaries must not be silently averaged.
    data = data.drop_duplicates()

    duplicated = data.duplicated(
        ["flight_line", "variable"],
        keep=False,
    )

    data.loc[duplicated, "measure"] = np.nan

    return data


def composition_valid(data, catalog):
    """
    Check whether benthic classes share a validated denominator.

    Stacked composition is allowed only when metadata and valid pixel
    counts support a common denominator and the source probabilities
    sum to approximately one.
    """
    if data.empty:
        return False

    required = {"valid_count", "unit_label"}

    if not required.issubset(data.columns):
        return False

    if not data["unit_label"].str.startswith("%").all():
        return False

    if data.duplicated(["flight_line", "variable"]).any():
        return False

    pivot = data.pivot(
        index="flight_line",
        columns="variable",
        values="measure",
    )

    required_classes = {"coral", "algae", "sand"}

    if not required_classes.issubset(pivot.columns):
        return False

    counts = (
        data.groupby("flight_line")["valid_count"]
        .nunique()
    )

    if (
        "flight_line" not in catalog
        or catalog["flight_line"].duplicated().any()
    ):
        return False

    quality = catalog.set_index("flight_line")

    required_quality = {
        "probability_sum_min",
        "probability_sum_max",
        "valid_benthic_pixels",
    }

    if not required_quality.issubset(quality.columns):
        return False

    quality = quality.reindex(pivot.index)

    common = (
        data.groupby("flight_line")["valid_count"]
        .first()
        .reindex(pivot.index)
    )

    return bool(
        (counts == 1).all()
        and (common > 0).all()
        and (common == quality["valid_benthic_pixels"]).all()
        and quality["probability_sum_min"].between(
            0.95,
            1.05,
        ).all()
        and quality["probability_sum_max"].between(
            0.95,
            1.05,
        ).all()
        and pivot[
            ["coral", "algae", "sand"]
        ].notna().all().all()
        and pivot[
            ["coral", "algae", "sand"]
        ].sum(axis=1).between(95, 105).all()
    )
