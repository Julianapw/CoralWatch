
# CoralWatch — Streamlit Data Contract

The data pipeline creates processed CSV and JSON files in `data/processed/`.

The Streamlit dashboard reads these files. It does not need to open the raw NASA or NOAA NetCDF files.

## Data sources

1. **NASA CORAL / PRISM L2-RBEN** — historical benthic observations, mainly from 2016–2017.
2. **NOAA Coral Reef Watch v3.1** — daily satellite products for thermal stress and bleaching-risk monitoring.

NASA and NOAA dates must remain separate. Recent NOAA conditions must not be presented as the cause of historical NASA observations.

## Processed files

| File | Purpose |
|---|---|
| `flight_catalog.csv` | NASA flight identifiers, regions, dates and geographic bounds. |
| `flight_inventory.csv` | Technical metadata for each NASA source file. |
| `variable_inventory.csv` | Variable names, units, descriptions, dimensions and valid ranges. |
| `benthic_variable_summary.csv` | Flight-level statistics for benthic variables. |
| `spatial_observations.csv` | Georeferenced NASA observations. |
| `class_legend.csv` | Source-provided classification values and meanings. |
| `dashboard_config.json` | NASA source, DOI, selected region and scientific notes. |
| `noaa_daily_summary.csv` | Recent daily regional means, minima, maxima, valid counts and BAA summaries. |
| `noaa_spatial_summary.csv` | Spatial summary and geographic bounds for each NOAA footprint. |
| `noaa_latest_map.csv` | Latest NOAA pixels with latitude, longitude, date, SST, SST anomaly, HotSpot, DHW and BAA. |
| `noaa_alert_summary.csv` | Latest pixel counts and percentages by BAA level. |
| `noaa_config.json` | NOAA product metadata and latest observation dates. |
| `noaa_sst_history_daily.csv` | Historical daily regional mean SST used for annual trends. |

## NOAA field names

### Daily regional summary

The dashboard adapts source column names to a common schema.

| Source field | Dashboard field | Meaning |
|---|---|---|
| `SST_mean` | `sst_mean` | Mean sea surface temperature (°C). |
| `SSTANOMALY_mean` | `anomaly_mean` | Mean SST anomaly (°C). |
| `HOTSPOT_mean` | `hotspot_mean` | Mean Coral Bleaching HotSpot (°C). |
| `DHW_mean` | `dhw_mean` | Mean Degree Heating Weeks (°C-weeks). |
| `DHW_max` | `dhw_max` | Maximum Degree Heating Weeks (°C-weeks). |
| `BAA_max` | `baa` | Source-provided 7-day maximum BAA code. |

### Latest pixel map

The pixel map requires:

- `region`
- `date`
- `latitude`
- `longitude`
- `CRW_SST`
- `CRW_SSTANOMALY`
- `CRW_HOTSPOT`
- `CRW_DHW`
- `CRW_BAA_7D_MAX`

Missing variables are not replaced with fabricated values.

## Long-term SST analysis

`noaa_sst_history_daily.csv` contains regional daily SST means.

The dashboard converts daily values into monthly means and then annual means.

Coverage requirements:

- At least 15 valid daily observations per month.
- At least 9 valid months per year.
- At least 10 valid years for statistical testing.

Trend methods:

- Theil-Sen slope, reported in °C per decade.
- Two-sided Mann-Kendall monotonic trend test.
- Benjamini-Hochberg adjustment across regions.
- 95% confidence interval for the Theil-Sen slope.

Serial autocorrelation is not corrected in the current exploratory implementation.

## Interpretation rules

1. NASA CORAL is historical; it does not measure current reef health.
2. The three NASA sample flights cover different geographic footprints.
3. Do not calculate a coral-cover trend from these three different flight footprints.
4. BAA is a NOAA source-provided classification, not a mortality diagnosis.
5. NOAA `pixel_percent` refers to valid ocean pixels in the selected geographic footprint, not the percentage of affected coral colonies.
6. NOAA geographic boxes are not necessarily reef-only masks.
7. Always display the observation date, source and unit.
8. Missing or invalid files must produce explanatory messages rather than fabricated results.
9. Do not infer causality between recent NOAA thermal conditions and historical NASA benthic observations.

## Sources

- NASA CORAL Browser: https://oceandata.sci.gsfc.nasa.gov/coral_browser/
- NASA CORAL L2/RBEN DOI: https://doi.org/10.5067/PRISM/CORAL/L2/RBEN/V1
- NOAA Coral Reef Watch v3.1: https://coralreefwatch.noaa.gov/product/5km/
- PacIOOS ERDDAP: https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.html
