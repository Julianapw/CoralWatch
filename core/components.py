"""Small, native presentation components and stable NASA display labels."""
from html import escape
import pandas as pd
import streamlit as st


def area_labels(catalog):
    """Derive labels from the complete catalog, never from the filtered subset."""
    if 'flight_line' not in catalog:
        return {}
    d = catalog.dropna(subset=['flight_line']).copy()
    d['_sort_code'] = d.flight_line.astype(str)
    if 'observation_date' in d:
        d = d.sort_values(['observation_date', '_sort_code'], kind='stable', na_position='last')
    else:
        d = d.sort_values('_sort_code', kind='stable')
    d = d.drop_duplicates('flight_line')
    result = {}
    for number, (_, row) in enumerate(d.iterrows(), 1):
        date = row.get('observation_date')
        suffix = f' · voo de {date:%d/%m/%Y}' if pd.notna(date) else ' · data não informada'
        result[row.flight_line] = f'Área {number:02d}' + suffix
    return result


def display_name(code):
    return st.session_state.get('_cw_area_labels', {}).get(code, str(code))


def display_frame(frame):
    """Add an axis label to a copy; source identifiers and values stay unchanged."""
    d = frame.copy()
    if 'flight_line' in d:
        d['_area'] = d.flight_line.map(display_name)
    return d


def data_source_badge(source):
    text = 'NASA CORAL · observações históricas' if source == 'NASA' else 'NOAA Coral Reef Watch · data observada'
    return f'<p class="cw-source">{text}</p>'


def section_header(title, subtitle='', source='NASA'):
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def kpi_card(title, value, detail, key, source='NASA'):
    st.metric(title, value)
    st.caption(detail)


def alert_card(code, title, count, detail):
    risk_pill(title, code)
    st.caption(f'{count} · {detail}')


def disclaimer():
    st.caption('NASA CORAL apresenta observações históricas. NOAA fornece indicadores de estresse térmico e risco de branqueamento na data informada. Esses dados não diagnosticam mortalidade individual de corais.')


def hero(title, subtitle):
    st.title(title)
    st.caption(subtitle)


def insight(text):
    st.caption(text)


def empty_chart(text):
    st.markdown(f'<div class="cw-empty"><strong>Sem observações disponíveis</strong>{escape(text)}</div>', unsafe_allow_html=True)


def summary_item(title, value):
    st.caption(title)
    st.write(str(value))


def risk_pill(text, code):
    category = str(int(code)) if code in range(5) else 'other'
    st.markdown(f'<span class="cw-risk cw-risk-{category}">{escape(text)}</span>', unsafe_allow_html=True)
