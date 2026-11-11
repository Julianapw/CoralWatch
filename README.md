
# CoralWatch

**Exploring historical reef composition and recent thermal stress in the Great Barrier Reef.**

CoralWatch combines historical benthic observations from **NASA CORAL / PRISM L2-RBEN** with thermal-stress indicators from **NOAA Coral Reef Watch v3.1**.

The project provides a Python data pipeline and a four-page Streamlit dashboard.

## Data sources

### NASA CORAL / PRISM L2-RBEN

NASA CORAL provides historical airborne observations of benthic classes, including coral, algae and sand.

The current sample contains three Great Barrier Reef flight footprints from 2016.

Source: https://oceandata.sci.gsfc.nasa.gov/coral_browser/

DOI: https://doi.org/10.5067/PRISM/CORAL/L2/RBEN/V1

### NOAA Coral Reef Watch v3.1

NOAA provides daily global satellite products at approximately 5-km resolution, including:

- Sea Surface Temperature (SST)
- SST anomaly
- Coral Bleaching HotSpot
- Degree Heating Weeks (DHW)
- Bleaching Alert Area (BAA), including the 7-day maximum

The product suite covers 1985 to the present.

Source: https://coralreefwatch.noaa.gov/product/5km/

## Project structure

```text
CoralWatch/
├── coralwatch/
│   ├── nasa.py
│   ├── noaa.py
│   ├── noaa_analysis.py
│   ├── pipeline.py
│   └── settings.py
├── core/
│   ├── components.py
│   ├── data.py
│   ├── filters.py
│   └── theme.py
├── dashboard/
│   ├── data.py
│   ├── charts.py
│   ├── trends.py
│   └── ui.py
├── data/
│   ├── raw/
│   └── processed/
├── downloads/
├── pages/
├── tests/
├── app.py
├── requirements.txt
└── run_pipeline.py
```

## Installation

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Prepare NASA data

Place NASA CORAL L2/RBEN NetCDF files in:

```text
data/raw/nasa/
```

Run the NASA processing pipeline:

```bash
python3 run_pipeline.py --source nasa
```

Processed files are written to `data/processed/`.

## Download recent NOAA data

Download the recent multi-variable time series for the selected flight footprints:

```bash
python3 -m coralwatch.noaa --days 30
```

## Download historical NOAA SST

Historical SST is downloaded separately and divided into requests of no more than 365 days:

```bash
python3 -m coralwatch.noaa \
  --days 30 \
  --history-days 15000 \
  --chunk-days 365
```

Add `--refresh` to download the files again, even when cached files exist.

The historical download is used for annual SST analysis. It is not necessary to download 40 years of every NOAA indicator to calculate the SST trend.

## Run the dashboard

```bash
python3 -m streamlit run app.py
```

Open the local address shown in the terminal, usually:

```text
http://localhost:8501
```

The dashboard reads processed files from `data/processed/`. It does not download or process NetCDF files when a page is opened.

## Dashboard pages

1. **Overview** — project summary, NASA flight footprints, historical composition and recent NOAA status.
2. **Reef Composition** — benthic class comparisons, coral ranking and observation distributions.
3. **Environmental Monitoring** — daily SST, DHW, HotSpot, SST anomaly, NOAA pixel map and long-term SST trends.
4. **Early Warning System** — NOAA Bleaching Alert Area levels, regional status and alert map.

## Long-term SST methodology

The historical trend workflow:

1. Calculates daily mean SST for each NOAA geographic footprint.
2. Calculates monthly means from valid daily regional means.
3. Requires at least 15 valid daily observations per month.
4. Requires at least 9 valid months per year.
5. Requires at least 10 valid years before statistical testing.
6. Estimates the slope using Theil-Sen.
7. Tests monotonic trend evidence with the two-sided Mann-Kendall test.
8. Applies Benjamini-Hochberg adjustment across the analyzed regions.

The slope is reported in °C per decade. The current implementation does not correct for serial autocorrelation; results are exploratory.

## Scientific limitations

- NASA CORAL observations are historical and do not describe current reef health.
- The three NASA flight footprints are different geographic areas. They must not be interpreted as repeated measurements of the same reef.
- Coral, algae and sand values are class probabilities, not automatically direct measurements of surface area.
- NOAA pixels describe ocean grid cells in the selected geographic footprints, not exclusively coral colonies.
- BAA is a source-provided classification, not a diagnosis of individual coral mortality.
- Present-day NOAA conditions are not treated as the cause of the historical 2016 NASA observations.
- Missing data do not indicate No Stress or ecological degradation.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Technologies

Python, pandas, NumPy, SciPy, NetCDF4, xarray, Streamlit, Plotly and PyDeck.
