
"""Project settings. Edit REGION_NAME and NOAA_BBOX_FALLBACK when needed."""
from pathlib import Path

# Project root is the folder that contains run_pipeline.py.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
NASA_RAW_DIR = RAW_DIR / "nasa"
NOAA_RAW_DIR = RAW_DIR / "noaa"
PROCESSED_DIR = DATA_DIR / "processed"
LOG_DIR = PROJECT_ROOT / "logs"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"

# NASA CORAL / PRISM L2-RBEN
REGION_NAME = "Great Barrier Reef"
MAX_SAMPLE_VALUES = 50_000
MAX_SPATIAL_ROWS_PER_VARIABLE = 100_000

# NOAA Coral Reef Watch v3.1
NOAA_DAYS = 30
NOAA_MAP_STRIDE = 1
NOAA_DATASET_ID = "dhw_5km"
NOAA_ERDDAP_BASE = (
    "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.nc"
)

# Used only if no valid geographic bounds can be extracted from NASA files.
NOAA_BBOX_FALLBACK = {
    "lat_min": -25.0,
    "lat_max": -10.0,
    "lon_min": 142.0,
    "lon_max": 155.0,
}

NOAA_ALERT_LABELS = {
    0: "No Stress",
    1: "Bleaching Watch",
    2: "Bleaching Warning",
    3: "Alert Level 1",
    4: "Alert Level 2",
}

NOAA_VARIABLES = [
    "CRW_BAA_7D_MAX",
    "CRW_DHW",
    "CRW_HOTSPOT",
    "CRW_SST",
    "CRW_SSTANOMALY",
]

NOAA_VAR_LABELS = {
    "CRW_BAA_7D_MAX": "Bleaching Alert Area (7-day maximum)",
    "CRW_DHW": "Degree Heating Weeks",
    "CRW_HOTSPOT": "Coral Bleaching HotSpot",
    "CRW_SST": "Sea Surface Temperature",
    "CRW_SSTANOMALY": "Sea Surface Temperature Anomaly",
}

NASA_OUTPUTS = [
    "flight_catalog.csv",
    "flight_inventory.csv",
    "variable_inventory.csv",
    "benthic_variable_summary.csv",
    "spatial_observations.csv",
    "class_legend.csv",
    "dashboard_config.json",
]

NOAA_OUTPUTS = [
    "noaa_thermal_timeseries.csv",
    "noaa_latest_map.csv",
    "noaa_alert_summary.csv",
    "noaa_config.json",
    "noaa_sst_history_daily.csv",
]
