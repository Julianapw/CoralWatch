"""Schema adaptation without importing or running the scientific pipeline."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'processed'
FILES = ('flight_catalog.csv', 'benthic_variable_summary.csv', 'spatial_observations.csv',
         'variable_inventory.csv', 'class_legend.csv', 'dashboard_config.json',
         'nasa_pixel_quality.csv', 'noaa_thermal_timeseries.csv', 'noaa_latest_map.csv',
         'noaa_alert_summary.csv', 'noaa_config.json', 'noaa_daily_summary.csv',
         'noaa_spatial_summary.csv', 'integrated_regional_summary.csv')
ALIASES = {
    'sst_mean': ('SST_mean', 'sst_c_mean'),
    'anomaly_mean': ('SSTANOMALY_mean', 'sst_anomaly_c_mean'),
    'hotspot_mean': ('HOTSPOT_mean', 'hotspot_c_mean'),
    'hotspot_max': ('HOTSPOT_max', 'hotspot_c_max'),
    'dhw_mean': ('DHW_mean', 'dhw_celsius_weeks_mean'),
    'dhw_max': ('DHW_max', 'dhw_celsius_weeks_max'),
    'baa': ('BAA_max', 'baa_7d_max', 'CRW_BAA_7D_MAX'),
    'sst': ('sst_c', 'CRW_SST'), 'hotspot': ('hotspot_c', 'CRW_HOTSPOT'),
    'dhw': ('dhw_celsius_weeks', 'CRW_DHW'),
}


def signature(directory):
    return tuple((name, (directory / name).stat().st_mtime_ns,
                  (directory / name).stat().st_size) for name in FILES if (directory / name).exists())


@st.cache_data(show_spinner=False)
def _read(directory, fingerprint):
    frames, configs, messages = {}, {}, []
    for name in FILES:
        path = Path(directory) / name
        if not path.exists():
            continue
        try:
            if path.suffix == '.json':
                obj = json.loads(path.read_text(encoding='utf-8-sig'))
                if not isinstance(obj, dict):
                    raise ValueError('objeto JSON esperado')
                configs[name] = obj
            else:
                frames[name] = pd.read_csv(path)
                if frames[name].empty:
                    messages.append(f'{name}: arquivo sem observações.')
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            messages.append(f'{name}: não foi possível carregar ({exc}).')
    return frames, configs, messages


def numeric(series):
    result = pd.to_numeric(series, errors='coerce')
    return result.mask(~np.isfinite(result) | result.isin([-999, -9999, -32767, -32768, 32767, 65535]))


def apply_metadata(d, inventory, column):
    """Respect declared valid ranges and fill values for each variable/file."""
    d = d.copy()
    if column not in d:
        return d
    d[column] = numeric(d[column])
    if not {'variable'} <= set(d) or 'variable' not in inventory:
        return d
    keys = ['variable'] + (['source_file'] if 'source_file' in d and 'source_file' in inventory else [])
    for _, meta in inventory.iterrows():
        mask = pd.Series(True, index=d.index)
        for key in keys:
            mask &= d[key] == meta[key]
        for field, operation in [('valid_min', 'min'), ('valid_max', 'max'),
                                 ('_FillValue', 'fill'), ('missing_value', 'fill')]:
            value = pd.to_numeric(meta.get(field), errors='coerce')
            if pd.notna(value):
                invalid = d[column] < value if operation == 'min' else d[column] > value if operation == 'max' else d[column] == value
                d.loc[mask & invalid, column] = np.nan
    return d


def dates(series):
    return pd.to_datetime(series, errors='coerce', utc=True, format='mixed').dt.tz_localize(None)


def adapt_noaa(frame, regional=False):
    d = frame.copy()
    if 'date' not in d or (regional and 'region' not in d):
        return pd.DataFrame()
    d['date'] = dates(d['date'])
    d = d.dropna(subset=['date'])
    if regional:
        d = d.dropna(subset=['region'])
        d['region'] = d['region'].astype(str).str.strip()
    else:
        d['region'] = 'Recorte global do arquivo (sem divisão regional)'
    for target, aliases in ALIASES.items():
        for source in aliases:
            if source in d:
                d[target] = numeric(d[source])
                break
    if 'baa' in d:
        d['baa'] = d['baa'].where((d['baa'] >= 0) & (d['baa'] % 1 == 0))
    return d.drop_duplicates(['region', 'date'], keep='last')


def latest_by_region(d):
    if d.empty or not {'region', 'date'} <= set(d):
        return pd.DataFrame()
    return d.sort_values('date').groupby('region', as_index=False).tail(1).copy()


def coordinates(frame):
    d = frame.copy()
    if not {'latitude', 'longitude'} <= set(d):
        return pd.DataFrame()
    for c in ('latitude', 'longitude'):
        d[c] = numeric(d[c])
    return d[d.latitude.between(-90, 90) & d.longitude.between(-180, 180)].copy()


def load(directory=None):
    directory = Path(directory) if directory is not None else DATA_DIR
    raw, config, messages = _read(str(directory), signature(directory))
    regional = adapt_noaa(raw.get('noaa_daily_summary.csv', pd.DataFrame()), True)
    original = adapt_noaa(raw.get('noaa_thermal_timeseries.csv', pd.DataFrame()))
    noaa, source = (regional, 'noaa_daily_summary.csv') if not regional.empty else (original, 'noaa_thermal_timeseries.csv')
    for name, required in [('noaa_daily_summary.csv', {'date', 'region'}),
                           ('noaa_thermal_timeseries.csv', {'date'}),
                           ('benthic_variable_summary.csv', {'variable', 'mean'})]:
        if name in raw and not raw[name].empty:
            missing = required - set(raw[name])
            if missing:
                messages.append(f'{name}: colunas necessárias ausentes: {sorted(missing)}.')
            if 'date' in raw[name] and dates(raw[name]['date']).isna().any():
                messages.append(f'{name}: datas inválidas excluídas.')
    catalog = raw.get('flight_catalog.csv', pd.DataFrame()).copy()
    integrated = raw.get('integrated_regional_summary.csv', pd.DataFrame())
    if catalog.empty and not integrated.empty:
        catalog = integrated.rename(columns={'nasa_region': 'region', 'nasa_observation_date': 'observation_date'}).copy()
        messages.append('Catálogo NASA: fallback integrated_regional_summary.csv; estatísticas NOAA do período não usadas como atuais.')
    if 'observation_date' in catalog:
        catalog['observation_date'] = dates(catalog.observation_date)
    benthic = raw.get('benthic_variable_summary.csv', pd.DataFrame()).copy()
    if benthic.empty and not integrated.empty:
        parts = []
        for variable in ('coral', 'algae', 'sand'):
            if variable + '_mean' in integrated:
                part = catalog.copy()
                part['variable'], part['mean'] = variable, numeric(integrated[variable + '_mean'])
                parts.append(part)
        benthic = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    benthic = prepare_benthic(benthic, catalog, raw, config)
    spatial = raw.get('spatial_observations.csv', pd.DataFrame()).copy()
    spatial = attach_catalog(spatial, catalog)
    spatial = apply_metadata(spatial, raw.get('variable_inventory.csv', pd.DataFrame()), 'value')
    if 'observation_date' in spatial:
        spatial['observation_date'] = dates(spatial.observation_date)
    pixels = coordinates(raw.get('noaa_latest_map.csv', pd.DataFrame()))
    for target, aliases in ALIASES.items():
        for col in aliases:
            if col in pixels:
                pixels[target] = numeric(pixels[col])
                break
    if 'date' in pixels:
        pixels['date'] = dates(pixels.date)
        pixels = pixels[pixels.date == pixels.date.max()]
    elif not pixels.empty:
        metadata = config.get('noaa_config.json', {})
        observed = metadata.get('latest_date', metadata.get('latest_observation_date'))
        pixels['date'] = dates(pd.Series([observed] * len(pixels), index=pixels.index))
        if pixels.date.isna().all():
            messages.append('noaa_latest_map.csv: data observada ausente; mapa recente indisponível.')
            pixels = pixels.iloc[0:0]
    if 'baa' in pixels:
        pixels['baa'] = pixels.baa.where((pixels.baa >= 0) & (pixels.baa % 1 == 0))
    return dict(raw=raw, config=config, messages=messages, catalog=catalog,
                benthic=benthic, spatial=spatial, noaa=noaa, source=source,
                regional=not regional.empty, pixels=pixels)


def attach_catalog(d, catalog):
    d = d.copy()
    for key in ('source_file', 'flight_line'):
        if key in d and key in catalog and not catalog[key].duplicated().any():
            extras = [c for c in ('flight_line', 'region', 'observation_date') if c in catalog and c not in d]
            if extras:
                d = d.merge(catalog[[key] + extras], on=key, how='left', validate='many_to_one')
            break
    return d


def prepare_benthic(d, catalog, raw, config):
    if not {'variable', 'mean'} <= set(d):
        return pd.DataFrame()
    d = attach_catalog(d, catalog)
    d = d[d.variable.isin(['coral', 'algae', 'sand'])].copy()
    if 'flight_line' not in d:
        return pd.DataFrame()
    # Metadata evidence, never a maximum-value heuristic.
    legend = raw.get('class_legend.csv', pd.DataFrame())
    inventory = raw.get('variable_inventory.csv', pd.DataFrame())
    d = apply_metadata(d, inventory, 'mean')
    if 'valid_count' in d:
        d.loc[numeric(d.valid_count) <= 0, 'mean'] = np.nan
    d['unit_label'] = 'unidade não confirmada'
    d['measure'] = numeric(d['mean'])
    for idx, row in d.iterrows():
        unit = str(row.get('units', '')).lower().strip()
        evidence = str(config.get('dashboard_config.json', {}).get('probability_note', '')).lower()
        meta = inventory
        if 'variable' in meta:
            meta = meta[meta.variable == row.variable]
            if 'source_file' in meta and 'source_file' in row:
                meta = meta[meta.source_file == row.source_file]
            if not unit or unit == 'nan':
                unit = str(meta.iloc[0].get('units', '')).lower() if not meta.empty else ''
        if 'variable' in legend:
            evidence += ' '.join(legend[legend.variable == row.variable].astype(str).values.ravel()).lower()
        if unit in ('%', 'percent', 'percentage'):
            d.loc[idx, 'unit_label'] = '% (medida declarada)'
            d.loc[idx, 'measure'] = numeric(pd.Series([row['mean']])).iloc[0]
        elif ('probabilit' in evidence and ('0 to 1' in evidence or '0–1' in evidence)):
            d.loc[idx, 'unit_label'] = '% de probabilidade média'
            d.loc[idx, 'measure'] = numeric(pd.Series([row['mean']])).iloc[0] * 100
        else:
            d.loc[idx, 'unit_label'] = unit or 'unidade não confirmada'
    percentage = d.unit_label.str.startswith('%')
    d.loc[percentage & ~d.measure.between(0, 100), 'measure'] = np.nan
    if 'observation_date' in d:
        d['observation_date'] = dates(d.observation_date)
    # Duplicate summaries are ambiguous: do not silently average or double count.
    d = d.drop_duplicates()
    duplicated = d.duplicated(['flight_line', 'variable'], keep=False)
    d.loc[duplicated, 'measure'] = np.nan
    return d


def composition_valid(d, catalog):
    if d.empty or not {'valid_count', 'unit_label'} <= set(d):
        return False
    if not d.unit_label.str.startswith('%').all():
        return False
    p = d.pivot(index='flight_line', columns='variable', values='measure') if not d.duplicated(['flight_line', 'variable']).any() else pd.DataFrame()
    if not {'coral', 'algae', 'sand'} <= set(p):
        return False
    counts = d.groupby('flight_line').valid_count.nunique()
    quality = catalog.set_index('flight_line') if 'flight_line' in catalog and not catalog.flight_line.duplicated().any() else pd.DataFrame()
    if not {'probability_sum_min', 'probability_sum_max', 'valid_benthic_pixels'} <= set(quality):
        return False
    q = quality.reindex(p.index)
    common = d.groupby('flight_line').valid_count.first().reindex(p.index)
    return bool((counts == 1).all() and (common > 0).all() and (common == q.valid_benthic_pixels).all()
                and q.probability_sum_min.between(.95, 1.05).all()
                and q.probability_sum_max.between(.95, 1.05).all()
                and p[['coral', 'algae', 'sand']].notna().all().all()
                and p.sum(axis=1).between(95, 105).all())
