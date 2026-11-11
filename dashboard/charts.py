"""Consistent Plotly and PyDeck presentation."""
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st
from dashboard.data import coordinates, numeric

BENTHIC = {'coral': '#008F95', 'algae': '#547C38', 'sand': '#D8B979'}
ALERTS = {0: 'No Stress', 1: 'Bleaching Watch', 2: 'Bleaching Warning', 3: 'Alert Level 1', 4: 'Alert Level 2'}
COLORS = {0: '#47A89B', 1: '#E7C84B', 2: '#EE923B', 3: '#D74B43', 4: '#872F65'}


def label(value):
    return 'Sem dados' if pd.isna(value) else ALERTS.get(value, f'Código BAA {value:g} — consultar metadados')


def plot(fig):
    fig.update_layout(template='plotly_white', font_color='#102D46', margin=dict(l=20, r=20, t=40, b=20), legend_title_text='')
    st.plotly_chart(fig, width='stretch')


def bounds_points(frame):
    d = frame.copy()
    required = ['latitude_min', 'latitude_max', 'longitude_min', 'longitude_max']
    if not set(required) <= set(d):
        return pd.DataFrame()
    for col in required:
        d[col] = numeric(d[col])
    d = d[d.latitude_min.between(-90, 90) & d.latitude_max.between(-90, 90)
          & d.longitude_min.between(-180, 180) & d.longitude_max.between(-180, 180)
          & (d.latitude_min <= d.latitude_max) & (d.longitude_min <= d.longitude_max)].copy()
    d['latitude'] = (d.latitude_min + d.latitude_max) / 2
    d['longitude'] = (d.longitude_min + d.longitude_max) / 2
    d['geometry_note'] = 'Centroide aproximado dos limites geográficos'
    return d


def map_chart(frame, value=None, categorical=False):
    d = coordinates(frame)
    if d.empty:
        st.info('Mapa indisponível: são necessárias coordenadas válidas ou limites geográficos no arquivo da fonte.')
        return
    if value and value in d:
        d[value] = numeric(d[value])
        d = d.dropna(subset=[value])
    if d.empty:
        st.info('Não há medidas válidas para este mapa.')
        return
    if len(d) > 50000:
        d = d.iloc[::max(2, (len(d) + 49999) // 50000)].copy()
        st.caption('Mapa: subamostra regular de até 50 mil pontos; tabelas e downloads mantêm os dados filtrados.')
    def rgb(code):
        color = COLORS.get(code, '#697687')
        return [int(color[i:i+2], 16) for i in (1, 3, 5)]
    if categorical and value in d:
        d['color'] = d[value].map(rgb)
        d['alert_label'] = d[value].map(label)
    elif value and value in d:
        low, high = d[value].min(), d[value].max()
        scaled = ((d[value] - low) / (high - low)) if high > low else pd.Series(.5, index=d.index)
        d['color'] = [[int(40 + 190 * x), int(170 - 100*x), int(190 - 130*x)] for x in scaled]
        st.caption(f'Escala {value}: turquesa {low:.2f} → laranja {high:.2f}.')
    else:
        d['color'] = [[0, 143, 149]] * len(d)
    tooltip_cols = [c for c in ('flight_line', 'region', 'date', 'observation_date', 'alert_label', value, 'geometry_note') if c and c in d]
    tooltip = '<br/>'.join(f'{c}: {{{c}}}' for c in dict.fromkeys(tooltip_cols))
    for col in d.select_dtypes(include=['datetime', 'datetimetz']).columns:
        d[col] = d[col].dt.strftime('%Y-%m-%d')
    layers = [pdk.Layer('ScatterplotLayer', d.to_dict('records'), get_position='[longitude, latitude]',
                        get_fill_color='color', get_radius=350, radius_min_pixels=4, pickable=True)]
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(
        latitude=float(d.latitude.mean()), longitude=float(d.longitude.mean()), zoom=4),
        map_style=pdk.map_styles.LIGHT, tooltip={'html': tooltip or 'Observação georreferenciada'}))
    if categorical:
        legend = ' &nbsp; '.join(f'<span style="color:{COLORS[k]}">●</span> {v}' for k, v in ALERTS.items())
        st.markdown(legend + ' &nbsp; <span style="color:#697687">●</span> Outros códigos', unsafe_allow_html=True)
