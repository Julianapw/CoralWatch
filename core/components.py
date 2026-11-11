"""Reusable presentation only; text interpolated into HTML is escaped."""
from html import escape
import streamlit as st
from core.theme import KPI_HEIGHT


def data_source_badge(source):
    if source == 'NASA':
        return '<span class="cw-badge cw-badge-nasa">NASA CORAL · Histórico 2016–2017</span>'
    return '<span class="cw-badge">NOAA Coral Reef Watch · Data observada</span>'


def section_header(title, subtitle='', source='NASA'):
    st.markdown(f'<div class="cw-section">{data_source_badge(source)}<h3>{escape(title)}</h3><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)


def kpi_card(title, value, detail, key, source='NASA'):
    with st.container(height=KPI_HEIGHT, border=False, key='cw-kpi-' + key):
        st.metric(title, value)
        st.markdown(data_source_badge(source), unsafe_allow_html=True)
        st.caption(detail)


def alert_card(code, title, count, detail):
    kpi_card(title, count, detail, f'baa-{code}', source='NOAA')


def disclaimer():
    st.markdown('<div class="cw-disclaimer">Os alertas indicam risco de branqueamento e estresse térmico, não diagnóstico de mortalidade. A cobertura bentônica sozinha não indica que um coral está morrendo.</div>', unsafe_allow_html=True)


def hero(title, subtitle):
    st.markdown(f'<div class="cw-hero"><div class="cw-eyebrow">NASA SPACE APPS · OCEAN SCIENCE</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)


def insight(text):
    st.markdown(f'<p class="cw-insight">{escape(text)}</p>', unsafe_allow_html=True)


def empty_chart(text):
    st.markdown(f'<div class="cw-empty"><strong>Sem observações disponíveis</strong><span>{escape(text)}</span></div>', unsafe_allow_html=True)


def summary_item(title, value):
    st.markdown(f'<div class="cw-summary-item"><small>{escape(title)}</small><strong>{escape(str(value))}</strong></div>', unsafe_allow_html=True)


def risk_pill(text, code):
    category = str(int(code)) if code in range(5) else 'other'
    st.markdown(f'<span class="cw-risk cw-risk-{category}">{escape(text)}</span>', unsafe_allow_html=True)
