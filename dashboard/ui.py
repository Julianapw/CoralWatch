"""Four pages, independent scientific time windows and explicit provenance."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.data import load, latest_by_region, composition_valid, coordinates, numeric, dates
from dashboard.charts import plot, map_chart, bounds_points, BENTHIC, ALERTS, COLORS, label

PAGES = ['Overview', 'Reef Composition (NASA CORAL)', 'Environmental Monitoring (NOAA)', 'Early Warning System']
NOTICE = ('NASA CORAL: observações históricas, principalmente de 2016–2017. NOAA: indicadores de estresse térmico e risco de branqueamento na data informada. Esses dados não diagnosticam mortalidade individual de corais.')


def table(d, name):
    st.dataframe(d, hide_index=True, width='stretch')
    st.download_button('Baixar dados filtrados (CSV)', d.to_csv(index=False).encode('utf-8-sig'), name + '.csv', 'text/csv', key='download_' + name)


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


def freshness(d):
    if d.empty or 'date' not in d:
        st.info('Sem observações NOAA no filtro. Necessário noaa_daily_summary.csv ou noaa_thermal_timeseries.csv com date válido.')
        return
    observed = d.date.max()
    st.caption(f'NOAA · última observação no filtro: {observed:%Y-%m-%d}. Cada região conserva sua própria data na tabela.')
    today = pd.Timestamp(datetime.now(ZoneInfo('America/Sao_Paulo')).date())
    if (today - observed.normalize()).days > 7:
        st.warning('Dados NOAA antigos: a observação mais recente selecionada tem mais de 7 dias. Não representa monitoramento em tempo real.')


def methodology(bundle):
    with st.expander('Metodologia e fontes'):
        st.write(NOTICE)
        st.write('Médias NASA usam os pixels válidos de cada voo; o card resume essas médias sem ponderação entre voos. Probabilidade de classe não é uma medição direta de área coberta. A mediana do produtor usa amostra regular. Classes nunca são renormalizadas; a seleção preserva o denominador original.')
        st.write('NOAA: prioridade determinística para noaa_daily_summary.csv; fallback noaa_thermal_timeseries.csv. Uma observação por região e data; em duplicatas exatas de chave, a última linha do arquivo prevalece. Indicadores regionais selecionam a última data de cada região dentro do filtro. BAA é o máximo de sete dias fornecido pela fonte; HotSpot e DHW são contexto, não uma reconstituição desse alerta.')
        st.write('noaa_spatial_summary.csv e a parte NOAA de integrated_regional_summary.csv resumem todo o intervalo. Não são usados como estado atual. Não replicamos séries globais entre voos nem relacionamos region a flight_line automaticamente. A combinação das fontes não demonstra causalidade nem tendência temporal. Baixa cobertura não comprova mortalidade.')
        st.write('Mapas de centroides são aproximações dos limites; mapas de pixels podem ser amostras. NOAA descreve pixels oceânicos do recorte (~5 km), não exclusivamente recifes. NASA tem resolução distinta (~7,9 m). Ausência de dados não equivale a No Stress.')
        st.markdown('[NASA CORAL](https://oceandata.sci.gsfc.nasa.gov/coral_browser/) · [DOI L2/RBEN](https://doi.org/10.5067/PRISM/CORAL/L2/RBEN/V1) · [NOAA CRW v3.1](https://coralreefwatch.noaa.gov/product/5km/index.php) · [PacIOOS ERDDAP](https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.html)')
        st.caption('Cache invalidado por nome, tamanho e data de modificação dos arquivos. A interface apenas lê dados processados; não baixa nem processa NetCDF.')
        for name, config in bundle['config'].items():
            st.write(name)
            st.json(config)
        if bundle['messages']:
            for message in bundle['messages']:
                st.warning(message)
        for name in ('variable_inventory.csv', 'class_legend.csv', 'nasa_pixel_quality.csv'):
            if name in bundle['raw']:
                st.write(name)
                st.dataframe(bundle['raw'][name], hide_index=True)


def recent_table(latest):
    cols = {'region': 'Região / recorte', 'date': 'Data observada', 'sst_mean': 'SST média (°C)',
            'hotspot_mean': 'HotSpot médio (°C)', 'hotspot_max': 'HotSpot máximo (°C)',
            'dhw_mean': 'DHW médio (°C-weeks)', 'dhw_max': 'DHW máximo (°C-weeks)', 'baa': 'BAA máximo de 7 dias'}
    return latest[[c for c in cols if c in latest]].rename(columns=cols)


def overview(bundle, cat, b, full, spatial, noaa, pixels):
    latest = latest_by_region(noaa)
    regions = cat['region'].nunique() if 'region' in cat else (full.region.nunique() if 'region' in full else 0)
    flights = cat['flight_line'].nunique() if 'flight_line' in cat else (b.flight_line.nunique() if 'flight_line' in b else 0)
    coral = full[full.variable == 'coral'] if 'variable' in full else pd.DataFrame()
    compatible = not coral.empty and coral.unit_label.nunique() == 1
    value = coral.measure.mean() if compatible else float('nan')
    baa = noaa[noaa.date == noaa.date.max()].baa.max() if not noaa.empty and 'baa' in noaa else (pixels.baa.max() if not pixels.empty and 'baa' in pixels else float('nan'))
    cols = st.columns(4)
    cols[0].metric('Regiões NASA identificadas', regions if regions else '—')
    cols[1].metric('Voos distintos', flights)
    cols[2].metric('Coral · média entre voos', f'{value:.1f}' if pd.notna(value) else '—')
    cols[3].metric('BAA · última data NOAA', label(baa))
    st.caption('Regiões são rótulos regionais do catálogo, não voos. Coral: média aritmética não ponderada das médias por voo; não representa cobertura de toda a área. ' + (str(coral.unit_label.iloc[0]) if compatible else 'Unidade comparável não disponível.'))
    if 'observation_date' in cat and cat.observation_date.notna().any():
        st.write(f'Período histórico NASA: {cat.observation_date.min():%Y-%m-%d} a {cat.observation_date.max():%Y-%m-%d}.')
    else:
        st.info('Período NASA indisponível: verifique flight_catalog.csv e observation_date.')
    freshness(noaa if not noaa.empty else pixels)
    layer = st.radio('Camada do mapa', ['NASA histórica', 'NOAA recente'], horizontal=True)
    if layer == 'NASA histórica':
        if not coordinates(spatial).empty:
            map_chart(spatial)
            st.caption('Observações NASA individuais; possível amostragem regular do produtor.')
        else:
            map_chart(bounds_points(cat))
            st.caption('Centro dos limites geográficos de cada voo — aproximação, não pixel observado.')
    else:
        map_chart(pixels, 'baa', True)
        if not pixels.empty:
            st.caption(f'Pixels NOAA observados em {pixels.date.max():%Y-%m-%d}; fonte noaa_latest_map.csv.')
    st.subheader('Resumo bentônico')
    if b.empty:
        st.info('Necessário benthic_variable_summary.csv com variable, mean e flight_line; metadados de unidade em class_legend.csv / variable_inventory.csv / dashboard_config.json.')
    else:
        table(b, 'overview_nasa')
    st.subheader('Resumo térmico · última observação por região')
    if not latest.empty:
        table(recent_table(latest), 'overview_noaa')


def composition(bundle, cat, b, full, spatial):
    if b.empty:
        st.info('Nenhuma medida bentônica neste filtro. Forneça benthic_variable_summary.csv e flight_catalog.csv ou ajuste os filtros.')
        return
    st.caption('As classes coral, algae e sand do produtor são probabilidades. Exibimos % de probabilidade média somente com evidência explícita de escala 0–1 nos metadados. Nenhum gráfico renormaliza os valores.')
    valid = composition_valid(full, cat)
    st.subheader('Classes bentônicas por voo')
    for unit, group in b.groupby('unit_label'):
        fig = px.bar(group, x='flight_line', y='measure', color='variable', color_discrete_map=BENTHIC,
                     barmode='stack' if valid else 'group', labels={'measure': unit, 'flight_line': 'Voo'})
        plot(fig)
    if valid:
        st.caption('Empilhamento validado: classes documentadas, contagens iguais ao conjunto comum válido e soma de probabilidades entre 0,95 e 1,05 em todos os pixels válidos. Valores originais, sem ajuste a 100%. Subconjuntos de classes podem não somar 100%.')
    else:
        st.info('Composição de 100% não validada: medidas exibidas lado a lado. São necessários metadados de unidade e métricas de denominador comum / soma no catálogo. Não reconstruímos pixels a partir de médias.')
    coral = b[b.variable == 'coral'].dropna(subset=['measure'])
    if not coral.empty:
        direction = st.radio('Ranking de coral', ['Maiores', 'Menores'], horizontal=True)
        ranked = coral.sort_values('measure', ascending=direction == 'Menores').head(20)
        plot(px.bar(ranked, x='measure', y='flight_line', orientation='h', color_discrete_sequence=[BENTHIC['coral']], labels={'measure': str(coral.unit_label.iloc[0]), 'flight_line': 'Voo'}))
    if not b.duplicated(['flight_line', 'variable']).any():
        pivot = b.pivot(index='flight_line', columns='variable', values='measure').reset_index()
        if {'coral', 'algae'} <= set(pivot) and b.unit_label.nunique() == 1:
            meta = b.drop_duplicates('flight_line')
            extra = [c for c in ('region', 'observation_date') if c in meta]
            pivot = pivot.merge(meta[['flight_line'] + extra], on='flight_line', validate='one_to_one')
            plot(px.scatter(pivot, x='coral', y='algae', hover_data=['flight_line'] + extra,
                            labels={'coral': 'Coral · ' + b.unit_label.iloc[0], 'algae': 'Algae · ' + b.unit_label.iloc[0]}, color_discrete_sequence=['#008F95']))
    individual = spatial[spatial.variable == 'coral'].copy() if 'variable' in spatial else pd.DataFrame()
    if 'value' in individual:
        individual['value'] = numeric(individual.value)
        individual = individual.dropna(subset=['value'])
    if not individual.empty and 'region' in individual and 'value' in individual:
        unit = str(individual['units'].iloc[0]) if 'units' in individual else 'unidade não confirmada'
        plot(px.box(individual, x='region', y='value', labels={'value': 'Coral · ' + unit, 'region': 'Região'}, color_discrete_sequence=[BENTHIC['coral']]))
        st.caption('Distribuição das observações individuais válidas exportadas em spatial_observations.csv; possível subamostra regular, na unidade original.')
    elif not coral.empty:
        group = 'region' if 'region' in coral else 'flight_line'
        plot(px.box(coral, x=group, y='measure', labels={'measure': coral.unit_label.iloc[0]}, color_discrete_sequence=[BENTHIC['coral']]))
        st.caption('Distribuição de médias entre voos; não representa a distribuição de pixels.')
    table(b, 'reef_composition')


def environmental(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    if noaa.empty:
        if not pixels.empty:
            st.info('Séries temporais ausentes; somente o mapa exportado está disponível.')
            available = [c for c in ('sst', 'hotspot', 'dhw') if c in pixels]
            if available:
                metric = st.selectbox('Indicador do mapa', available)
                map_chart(pixels, metric)
        return
    metrics = [('sst_mean', 'SST média (°C)'), ('anomaly_mean', 'Anomalia térmica média (°C)'),
               ('dhw_mean', 'DHW médio (°C-weeks)'), ('dhw_max', 'DHW máximo (°C-weeks)'),
               ('hotspot_mean', 'HotSpot médio (°C)')]
    for key, title in metrics:
        if key in noaa and noaa[key].notna().any():
            fig = px.line(noaa.sort_values('date'), x='date', y=key, color='region', markers=True,
                          title=title, labels={key: title, 'date': 'Data observada', 'region': 'Região / recorte'})
            if key.startswith('dhw'):
                for threshold in (4, 8):
                    fig.add_hline(y=threshold, line_dash='dash', annotation_text=f'{threshold} °C-weeks')
            plot(fig)
        elif key != 'dhw_max':
            st.info(f'{title}: coluna não disponível na fonte selecionada.')
    st.subheader('Indicadores · última observação por região')
    table(recent_table(latest_by_region(noaa)), 'latest_environmental')
    st.subheader('Mapa térmico · pixels recentes')
    available = [c for c in ('sst', 'hotspot', 'dhw') if c in pixels]
    if available:
        metric = st.selectbox('Indicador do mapa', available, format_func=lambda c: {'sst': 'SST (°C)', 'hotspot': 'HotSpot (°C)', 'dhw': 'DHW (°C-weeks)'}[c])
        map_chart(pixels, metric)
        st.caption('Fonte noaa_latest_map.csv; data(s): ' + ', '.join(pixels.date.dt.strftime('%Y-%m-%d').dropna().unique()))
    else:
        st.info('Mapa térmico requer noaa_latest_map.csv com coordenadas, data e medidas. Mapas globais não respondem ao filtro regional sem região explícita.')
    table(noaa, 'environmental_timeseries')


def warning_page(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    latest = latest_by_region(noaa)
    regional = bundle['regional'] and not latest.empty and 'baa' in latest
    if regional:
        alerts = latest.copy()
        counts = alerts.baa.value_counts()
        st.caption(f'Unidade: regiões/recortes NOAA identificados ({len(alerts)}); última data disponível por região dentro do filtro. BAA máximo de sete dias fornecido pela fonte.')
    elif not pixels.empty and 'baa' in pixels:
        alerts = pixels[pixels.baa.notna()].copy()
        counts = alerts.baa.value_counts()
        st.caption(f'Denominador: {len(alerts)} pixels oceânicos com BAA válido no mapa exportado, não percentual de recifes afetados. Data: {pixels.date.max():%Y-%m-%d}.')
    else:
        alerts, counts = pd.DataFrame(), pd.Series(dtype=float)
        st.info('Sem classificação regional ou pixels BAA datados. Ausência de dados não equivale a No Stress.')
        if not latest.empty and 'baa' in latest:
            st.write('BAA do recorte global: ' + label(latest.baa.iloc[0]))
        summary = bundle['raw'].get('noaa_alert_summary.csv', pd.DataFrame())
        if not summary.empty:
            st.caption('Resumo original fornecido; sem mapa datado não é usado para contagens de alerta atual.')
            st.dataframe(summary)
    cols = st.columns(5)
    for col, (code, name) in zip(cols, ALERTS.items()):
        count = int(counts.get(code, 0)) if not alerts.empty else None
        col.metric(name, count if count is not None else '—')
        col.markdown(f'<span style="color:{COLORS[code]}">●</span> BAA {code}', unsafe_allow_html=True)
        if count is not None and not regional:
            col.caption(f'{100 * count / len(alerts):.1f}% dos pixels válidos')
    if regional:
        missing = int(latest.baa.isna().sum())
        if missing:
            st.warning(f'{missing} região(ões) sem classificação; excluídas das cinco categorias.')
    if not alerts.empty:
        extra = alerts[alerts.baa.notna() & ~alerts.baa.isin(ALERTS)]
        if not extra.empty:
            st.warning('Códigos adicionais preservados: ' + ', '.join(str(x) for x in extra.baa.unique()) + '. Consulte noaa_config.json / metadados da fonte.')
        alerts['Nível'] = alerts.baa.map(label)
        alerts['Interpretação'] = 'BAA fornecido pela fonte (máximo de 7 dias); HotSpot/DHW do dia são apenas contexto.'
        cols_show = [c for c in ('region', 'latitude', 'longitude', 'date', 'baa', 'Nível', 'hotspot_mean', 'hotspot_max', 'dhw_mean', 'dhw_max', 'hotspot', 'dhw', 'Interpretação') if c in alerts]
        st.caption('HotSpot: °C; DHW: °C-weeks. Sufixos _mean = média regional, _max = máximo regional; sem sufixo = valor do pixel.')
        table(alerts[cols_show], 'early_warning')
    if not pixels.empty:
        map_chart(pixels, 'baa', True)
    elif regional:
        # Spatial summary is used exclusively for geometry, never period maxima.
        geometry = bundle['raw'].get('noaa_spatial_summary.csv', pd.DataFrame())
        if 'region' in geometry and not geometry.region.duplicated().any():
            bounds = [c for c in ('latitude_min', 'latitude_max', 'longitude_min', 'longitude_max') if c in geometry]
            mapped = latest.merge(geometry[['region'] + bounds], on='region', how='left', validate='one_to_one')
            map_chart(bounds_points(mapped), 'baa', True)
            st.caption('Centroides aproximados de recortes regionais. Somente os limites vêm do resumo espacial; os alertas vêm do resumo diário.')
        else:
            st.info('Mapa categórico requer noaa_latest_map.csv ou limites regionais em noaa_spatial_summary.csv.')
    if noaa.empty:
        for name in ('noaa_spatial_summary.csv', 'integrated_regional_summary.csv'):
            historical = bundle['raw'].get(name, pd.DataFrame())
            if not historical.empty:
                st.warning(f'{name}: resumo histórico de todo o intervalo; não é alerta atual.')
                table(historical, 'historical_' + name)


def main():
    st.set_page_config(page_title='CoralWatch', page_icon='🌊', layout='wide')
    st.sidebar.title('CoralWatch')
    st.sidebar.caption('Composição histórica e contexto térmico')
    page = st.sidebar.radio('Navegação', PAGES, key='page')
    if st.sidebar.button('Atualizar cache'):
        st.cache_data.clear()
    bundle = load()
    st.title(page)
    st.caption('CORALWATCH · NASA CORAL / NOAA CORAL REEF WATCH')
    st.info(NOTICE)
    st.caption(f'Fonte NOAA temporal: {bundle["source"]}' + (' (indisponível ou sem observações válidas).' if bundle['noaa'].empty else '.') + ' NASA: flight_catalog.csv e benthic_variable_summary.csv; fallback integrado informado na metodologia.')
    if not bundle['raw']:
        st.warning('Nenhum CSV disponível em data/processed/. Coloque os arquivos processados nessa pasta. Nenhum dado fictício é gerado.')
    cat, b, full, spatial = nasa_filters(bundle)
    noaa, pixels = noaa_filters(bundle)
    if page == PAGES[0]:
        overview(bundle, cat, b, full, spatial, noaa, pixels)
    elif page == PAGES[1]:
        composition(bundle, cat, b, full, spatial)
    elif page == PAGES[2]:
        environmental(bundle, noaa, pixels)
    else:
        warning_page(bundle, noaa, pixels)
    methodology(bundle)
