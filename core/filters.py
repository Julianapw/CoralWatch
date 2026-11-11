"""Shared sidebar filters; existing source-specific selection rules are preserved."""
import streamlit as st


def date_filter(d, column, title, key):
    if column not in d or d[column].dropna().empty:
        st.sidebar.caption(f'{title}: datas válidas indisponíveis.')
        return d
    lo, hi = d[column].min().date(), d[column].max().date()
    interval = st.sidebar.date_input(title, (lo, hi), min_value=lo, max_value=hi, key=key)
    if len(interval) != 2:
        st.sidebar.caption('Selecione o início e o fim do intervalo.')
        return d.iloc[0:0]
    return d[d[column].dt.date.between(*interval)]


def choice_filter(d, column, title, key):
    if column not in d or d[column].dropna().empty:
        st.sidebar.caption(f'{title}: campo indisponível.')
        return d
    options = sorted(d[column].dropna().unique().tolist(), key=str)
    selected = st.sidebar.multiselect(title, options, default=options, key=key)
    return d[d[column].isin(selected)]


def nasa_filters(bundle):
    st.sidebar.markdown('**NASA · campanha histórica**')
    cat = bundle['catalog'].copy()
    b = bundle['benthic'].copy()
    # Filter against the catalog when available, otherwise the summary metadata.
    base = cat if not cat.empty else b
    for col, title in [('region', 'Região NASA'), ('flight_line', 'Identificação do voo'), ('geographic_region', 'Região geográfica')]:
        base = choice_filter(base, col, title, 'nasa_' + col)
    base = date_filter(base, 'observation_date', 'Data da pesquisa NASA', 'nasa_dates')
    if 'flight_line' in base:
        flights = base.flight_line.unique()
        if 'flight_line' in b:
            b = b[b.flight_line.isin(flights)]
        if 'flight_line' in cat:
            cat = cat[cat.flight_line.isin(flights)]
    elif base.empty:
        b, cat = b.iloc[0:0], cat.iloc[0:0]
    full = b.copy()
    b = choice_filter(b, 'variable', 'Classe bentônica', 'classes')
    spatial = bundle['spatial'].copy()
    if not spatial.empty:
        if 'flight_line' in spatial and 'flight_line' in base:
            spatial = spatial[spatial.flight_line.isin(base.flight_line)]
        elif 'source_file' in spatial and 'source_file' in base:
            spatial = spatial[spatial.source_file.isin(base.source_file)]
        else:
            spatial = spatial.iloc[0:0]
        if 'variable' in spatial and 'variable' in b:
            spatial = spatial[spatial.variable.isin(b.variable)]
    return cat, b, full, spatial


def noaa_filters(bundle):
    st.sidebar.markdown('**NOAA · janela independente**')
    d = bundle['noaa'].copy()
    if bundle['regional']:
        d = choice_filter(d, 'region', 'Região NOAA', 'noaa_region')
    else:
        st.sidebar.caption('Série original: recorte global; sem filtro regional. Filtros NASA não alteram NOAA.')
    pixels = bundle['pixels'].copy()
    if d.empty and bundle['noaa'].empty and not pixels.empty:
        pixels = date_filter(pixels, 'date', 'Datas NOAA (pixels)', 'noaa_pixel_dates')
    else:
        d = date_filter(d, 'date', 'Datas NOAA', 'noaa_dates')
    if not pixels.empty:
        if bundle['regional']:
            # A global pixel map must not pretend to answer a regional filter.
            if 'region' in pixels:
                pixels = pixels[pixels.region.isin(d.region.unique())] if 'region' in d else pixels.iloc[0:0]
            else:
                pixels = pixels.iloc[0:0]
        if 'date' in d and not d.empty:
            pixels = pixels[pixels.date.between(d.date.min(), d.date.max())]
        elif not bundle['noaa'].empty:
            pixels = pixels.iloc[0:0]
    return d, pixels



def clear_filters():
    for key in list(st.session_state):
        if key.startswith(('nasa_', 'noaa_')) or key == 'classes':
            del st.session_state[key]


def render_filters(bundle):
    st.sidebar.button('Limpar filtros', on_click=clear_filters, width='stretch')
    cat, b, full, spatial = nasa_filters(bundle)
    noaa, pixels = noaa_filters(bundle)
    st.sidebar.caption(f'{len(b):,} registros bentônicos · {len(noaa):,} registros NOAA selecionados')
    st.sidebar.caption('Filtros de voo, pesquisa e classe NASA não se aplicam à fonte NOAA.')
    return cat, b, full, spatial, noaa, pixels
