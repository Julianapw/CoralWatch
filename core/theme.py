"""Light, restrained visual system. No data or filter logic lives here."""
import plotly.graph_objects as go
import streamlit as st

CHART_HEIGHT = 440
MAP_HEIGHT = 520
BENTHIC = {'coral': '#00877F', 'algae': '#67854B', 'sand': '#C5AE7C'}
ALERT_COLORS = {0: '#4FA3E0', 1: '#FFF06A', 2: '#FFB000', 3: '#FF4D2E', 4: '#B3001B'}
SERIES_COLORS = ['#00877F', '#406D9B', '#67854B', '#8C709C', '#92734C']

CSS = '''
.block-container { max-width:1480px; padding-top:2rem; padding-bottom:3rem; }
h1,h2,h3 { color:#173B4B; letter-spacing:-.025em; }
h1 { font-size:2rem; } h2 { font-size:1.45rem; } h3 { font-size:1.15rem; }
.cw-source { color:#516774; font-size:.78rem; line-height:1.5; margin:0 0 .75rem; }
.cw-risk { display:inline-block; padding:.15rem .55rem; border-radius:4px; font-size:.85rem; font-weight:600; }
.cw-risk-0 { color:#155781; background:#EAF4FB; }
.cw-risk-1 { color:#665600; background:#FFF9CE; }
.cw-risk-2 { color:#7A4C00; background:#FFF0D1; }
.cw-risk-3 { color:#A02A16; background:#FDECE7; }
.cw-risk-4 { color:#96001A; background:#FCE9ED; }
.cw-risk-other { color:#516774; background:#F0F3F4; }
.cw-legend { display:flex; flex-wrap:wrap; gap:.6rem 1rem; margin:.5rem 0 1rem; font-size:.8rem; color:#354F5C; }
.cw-legend span { white-space:normal; }
.cw-empty { padding:1.25rem 0; color:#516774; line-height:1.6; }
.cw-empty strong { display:block; color:#354F5C; margin-bottom:.35rem; }
@media(max-width:700px) { .block-container { padding-left:1rem; padding-right:1rem; } }
'''


def apply_theme():
    st.markdown('<style>' + CSS + '</style>', unsafe_allow_html=True)


def plotly_template():
    axis = dict(gridcolor='rgba(23,59,75,.08)', zeroline=False, automargin=True,
                tickfont=dict(color='#516774'), linecolor='rgba(23,59,75,.15)')
    return go.layout.Template(layout=go.Layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='Arial, sans-serif', color='#173B4B', size=13),
        colorway=SERIES_COLORS,
        xaxis=axis, yaxis=axis, margin=dict(l=10, r=10, t=55, b=20),
        hoverlabel=dict(bgcolor='#FFFFFF', bordercolor='#00877F', font_color='#173B4B'),
        legend=dict(orientation='h', yanchor='bottom', y=1.04, xanchor='left', x=0),
        modebar=dict(orientation='v', color='#516774', activecolor='#00877F', bgcolor='rgba(255,255,255,.9)'),
    ))
