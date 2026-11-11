"""One visual system for page spacing, cards, maps and Plotly figures."""
import plotly.graph_objects as go
import streamlit as st

CHART_HEIGHT = 360
PANEL_HEIGHT = 700
MAP_HEIGHT = 450
KPI_HEIGHT = 260
BENTHIC = {'coral': '#FF7A59', 'algae': '#7BC67E', 'sand': '#E8D3A2'}
ALERT_COLORS = {0: '#4FA3E0', 1: '#FFF06A', 2: '#FFB000', 3: '#FF4D2E', 4: '#B3001B'}

CSS = '''
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root { --cw-accent:#007F83; --cw-muted:#526B7D; --cw-border:rgba(0,127,131,.18); }
.stApp { background-color:#F8FBFD; color:#102D46; background-image:radial-gradient(ellipse at 60% 0%,rgba(0,153,158,.055),transparent 45%); }
#MainMenu, footer { visibility:hidden; }
/* Keep the native sidebar toggle accessible when the sidebar is collapsed. */
[data-testid="stHeader"] { background:transparent; }
[data-testid="stToolbar"] { visibility:hidden; }
.block-container { padding-top:1.5rem; padding-bottom:2.5rem; max-width:1500px; }
html,body,[data-testid="stAppViewContainer"] { font-family:'IBM Plex Sans',sans-serif; }
h1,h2,h3,[data-testid="stMetricValue"] { font-family:'Space Grotesk',sans-serif; }
h1 { letter-spacing:-.04em; }
[data-testid="stSidebar"] { background:#EDF5F8; border-right:1px solid var(--cw-border); }
[data-testid="stSidebar"] .block-container { padding-top:1.5rem; }
[data-testid="stVerticalBlock"] { gap:1rem; }
[data-testid="stHorizontalBlock"] { gap:1.25rem; align-items:stretch; }
[class*="st-key-cw-panel"], [class*="st-key-cw-kpi"] {
 background:linear-gradient(180deg,#FFFFFF,#F7FBFC);
 border:1px solid var(--cw-border)!important; border-radius:16px!important;
 box-shadow:0 8px 30px -12px rgba(16,45,70,.12); padding:20px!important;
 transition:border-color .2s,transform .2s; box-sizing:border-box;
}
[class*="st-key-cw-kpi"]:hover { border-color:#007F83!important; transform:translateY(-2px); }
[class*="st-key-cw-panel"]:hover { border-color:rgba(0,127,131,.35)!important; }
[class*="st-key-cw-kpi"] [data-testid="stVerticalBlock"] { gap:.5rem; }
[data-testid="stMetricLabel"] { color:#526B7D; text-transform:uppercase; letter-spacing:.1em; font-size:.72rem; min-height:2.6rem; }
[data-testid="stMetricLabel"] p { white-space:normal; }
[data-testid="stMetricValue"] { font-size:2.2rem; line-height:1.15; font-variant-numeric:tabular-nums; min-height:4.2rem; }
[data-testid="stMetricValue"] > div { white-space:normal; overflow:visible; overflow-wrap:anywhere; font-size:inherit; }
[class*="st-key-cw-kpi-alert"] [data-testid="stMetricValue"] { font-size:1.35rem; }
[class*="st-key-cw-kpi-baa-0"] { border-top:4px solid #4FA3E0!important; }
[class*="st-key-cw-kpi-baa-1"] { border-top:4px solid #FFF06A!important; }
[class*="st-key-cw-kpi-baa-2"] { border-top:4px solid #FFB000!important; }
[class*="st-key-cw-kpi-baa-3"] { border-top:4px solid #FF4D2E!important; }
[class*="st-key-cw-kpi-baa-4"] { border-top:4px solid #B3001B!important; }
.cw-eyebrow { color:#007F83; letter-spacing:.16em; font-size:.7rem; font-weight:600; text-transform:uppercase; margin-bottom:.6rem; }
.cw-hero { margin:.25rem 0 1rem; }
.cw-hero h1 { font-size:clamp(2rem,4vw,3.7rem); line-height:1.1; margin:0 0 .7rem; padding:0; }
.cw-hero p { color:#526B7D; margin:0; max-width:75ch; }
.cw-section { min-height:80px; margin:0; }
.cw-section h3 { font-size:1.12rem; margin:.4rem 0 .2rem; padding:0; }
.cw-section p { font-size:.82rem; line-height:1.5; color:#526B7D; margin:0; }
.cw-badge { display:inline-block; border:1px solid var(--cw-border); background:rgba(0,127,131,.06); color:#007F83; padding:4px 9px; border-radius:50px; font-size:.65rem; letter-spacing:.035em; }
.cw-badge-nasa { color:#B4432A; border-color:rgba(255,122,89,.24); background:rgba(255,122,89,.06); }
.cw-disclaimer { border-left:3px solid #FFF06A; background:#FFF9E6; border-radius:0 10px 10px 0; padding:14px 18px; color:#28465C; font-size:.85rem; line-height:1.6; margin:1rem 0; }
.cw-insight { min-height:3.1rem; color:#526B7D; font-size:.8rem; line-height:1.5; margin:0; }
.cw-summary-item { border-bottom:1px solid var(--cw-border); padding:14px 0; }
.cw-summary-item small { display:block; color:#526B7D; font-size:.75rem; }
.cw-summary-item strong { display:block; color:#102D46; font-size:1rem; margin-top:4px; overflow-wrap:anywhere; }
.cw-risk { display:inline-block; border:1px solid currentColor; border-radius:40px; padding:4px 10px; font-size:.75rem; }
.cw-risk-0 { color:#1C659B; background:#EFF7FD; } .cw-risk-1 { color:#756200; background:#FFFCE1; } .cw-risk-2 { color:#855700; background:#FFF5DA; }
.cw-risk-3 { color:#BF321B; background:#FFF0EB; } .cw-risk-4 { color:#B3001B; } .cw-risk-other { color:#526B7D; }
.cw-empty { height:360px; display:flex; align-items:center; justify-content:center; flex-direction:column; padding:24px; color:#526B7D; text-align:center; border:1px dashed var(--cw-border); border-radius:12px; box-sizing:border-box; }
.cw-empty strong { color:#28465C; margin-bottom:10px; }
[data-baseweb="tab-list"] { gap:.5rem; background:transparent; }
[data-baseweb="tab"] { background:#F1F7FA; border-radius:40px; padding:8px 18px; }
[aria-selected="true"][data-baseweb="tab"] { color:#007F83; background:rgba(0,127,131,.09); }
[data-testid="stAlert"] { border-radius:12px; }
[data-testid="stCaptionContainer"] { color:#526B7D; line-height:1.5; }
@media(max-width:900px) {
 [data-testid="stHorizontalBlock"] { flex-wrap:wrap; }
 [data-testid="stColumn"] { min-width:min(100%,320px)!important; flex:1 1 320px!important; }
 .block-container { padding-left:1rem; padding-right:1rem; }
}
'''


def apply_theme():
    st.markdown('<style>' + CSS + '</style>', unsafe_allow_html=True)


def plotly_template():
    axis = dict(gridcolor='rgba(16,45,70,.08)', zeroline=False, automargin=True,
                tickfont=dict(color='#526B7D'), linecolor='rgba(16,45,70,.14)')
    return go.layout.Template(layout=go.Layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family='IBM Plex Sans, sans-serif', color='#28465C', size=12),
        colorway=['#007F83', '#FF7A59', '#4FA3E0', '#7BC67E', '#E8D3A2', '#A18CDF'],
        xaxis=axis, yaxis=axis, margin=dict(l=10, r=10, t=48, b=10),
        hoverlabel=dict(bgcolor='#F1F7FA', bordercolor='#007F83', font_color='#102D46'),
        legend=dict(orientation='h', yanchor='bottom', y=1.04, xanchor='left', x=0),
    ))
