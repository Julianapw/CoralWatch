"""Four pages, independent scientific time windows and explicit provenance."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.data import latest_by_region, composition_valid, coordinates, numeric
from dashboard.charts import plot, map_chart, bounds_points, BENTHIC, ALERTS, label
from core.theme import PANEL_HEIGHT
from core.components import (kpi_card, alert_card, section_header, disclaimer,
                             hero, insight, empty_chart, summary_item, data_source_badge, risk_pill)
from core.data import load_bundle, load_nasa, load_noaa
from core.filters import render_filters
from core.theme import apply_theme

PAGES = ['Overview', 'Reef Composition (NASA CORAL)', 'Environmental Monitoring (NOAA)', 'Early Warning System']
NOTICE = ('NASA CORAL: observações históricas, principalmente de 2016–2017. NOAA: indicadores de estresse térmico e risco de branqueamento na data informada. Esses dados não diagnosticam mortalidade individual de corais.')


def table(d, name):
    st.dataframe(d, hide_index=True, width='stretch')
    st.download_button('Baixar dados filtrados (CSV)', d.to_csv(index=False).encode('utf-8-sig'), name + '.csv', 'text/csv', key='download_' + name)


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
    cols = st.columns(4, gap='medium')
    with cols[0]:
        kpi_card('Regiões NASA identificadas', regions if regions else '—', 'Rótulos regionais do catálogo; voos são contados separadamente.', 'regions')
    with cols[1]:
        kpi_card('Voos distintos', flights, 'Campanha histórica · filtros NASA selecionados.', 'flights')
    with cols[2]:
        kpi_card('Coral · média entre voos', f'{value:.1f}' if pd.notna(value) else '—', str(coral.unit_label.iloc[0]) if compatible else 'Unidade comparável indisponível.', 'coral')
    with cols[3]:
        kpi_card('BAA · última data NOAA', label(baa), 'Maior nível observado; máximo de sete dias da fonte.', 'alert-max', 'NOAA')
    st.caption('Regiões são rótulos regionais do catálogo, não voos. Coral: média aritmética não ponderada das médias por voo; não representa cobertura de toda a área. ' + (str(coral.unit_label.iloc[0]) if compatible else 'Unidade comparável não disponível.'))
    if 'observation_date' in cat and cat.observation_date.notna().any():
        st.write(f'Período histórico NASA: {cat.observation_date.min():%Y-%m-%d} a {cat.observation_date.max():%Y-%m-%d}.')
    else:
        st.info('Período NASA indisponível: verifique flight_catalog.csv e observation_date.')
    freshness(noaa if not noaa.empty else pixels)
    layer = st.radio('Camada do mapa', ['NASA histórica', 'NOAA recente'], horizontal=True)
    left, right = st.columns([2, 1], gap='medium')
    with left, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-overview-map'):
        section_header('Área de observação', 'Explore o recorte espacial da fonte selecionada.', 'NASA' if layer == 'NASA histórica' else 'NOAA')
        if layer == 'NASA histórica':
            points = spatial[spatial.variable == 'coral'].copy() if 'variable' in spatial else spatial
            if not coordinates(points).empty:
                map_chart(points, 'value' if 'value' in points else None)
                st.caption('Observações NASA individuais; possível amostragem regular do produtor. Cor pelo valor original da probabilidade de coral, sem renormalização.')
            elif not coordinates(spatial).empty:
                map_chart(spatial)
                st.caption('Observações NASA individuais; possível amostragem regular do produtor.')
            else:
                map_chart(bounds_points(cat))
                st.caption('Centro dos limites geográficos de cada voo — aproximação, não pixel observado.')
        else:
            map_chart(pixels, 'baa', True)
            if not pixels.empty:
                st.caption(f'Pixels NOAA observados em {pixels.date.max():%Y-%m-%d}; fonte noaa_latest_map.csv.')
    with right, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-overview-summary'):
        section_header('Principais indicadores', 'Leitura histórica e térmica em contextos separados.', 'NASA')
        valid_coral = coral.dropna(subset=['measure']) if not coral.empty else coral
        if compatible and not valid_coral.empty:
            for title, row in [('Maior média de coral entre voos', valid_coral.loc[valid_coral.measure.idxmax()]), ('Menor média de coral entre voos', valid_coral.loc[valid_coral.measure.idxmin()])]:
                summary_item(title, f'{row.flight_line} · {row.measure:.1f} {row.unit_label}')
        else:
            summary_item('Coral', 'Sem medidas comparáveis no filtro')
        st.markdown(data_source_badge('NOAA'), unsafe_allow_html=True)
        if 'baa' in latest and latest.baa.notna().any():
            row = latest.loc[latest.baa.idxmax()]
            summary_item('Recorte com maior BAA regional', f'{row.region} · {label(row.baa)} · {row.date:%Y-%m-%d}')
            summary_item('Datas regionais', 'Cada região conserva sua última observação no filtro.')
        else:
            summary_item('Estresse térmico regional', 'Sem classificação regional disponível')
        insight('BAA é fornecido pela NOAA. HotSpot e DHW do dia são contexto e não reconstituem o máximo de sete dias.')
    section_header('Resumo bentônico', 'Estatísticas e metadados completos dos registros selecionados.', 'NASA')
    if b.empty:
        st.info('Necessário benthic_variable_summary.csv com variable, mean e flight_line; metadados de unidade em class_legend.csv / variable_inventory.csv / dashboard_config.json.')
    else:
        table(b, 'overview_nasa')
    section_header('Resumo térmico · última observação por região', 'Médias e máximos mantêm os rótulos e as unidades originais.', 'NOAA')
    if not latest.empty:
        table(recent_table(latest), 'overview_noaa')


def composition(bundle, cat, b, full, spatial):
    st.caption('As classes coral, algae e sand do produtor são probabilidades. Exibimos % de probabilidade média somente com evidência explícita de escala 0–1 nos metadados. Nenhum gráfico renormaliza os valores.')
    if b.empty:
        st.info('Nenhuma medida bentônica neste filtro. Forneça benthic_variable_summary.csv e flight_catalog.csv ou ajuste os filtros.')
    valid = composition_valid(full, cat)
    coral = b[b.variable == 'coral'].dropna(subset=['measure']) if 'variable' in b else pd.DataFrame()
    left, right = st.columns(2, gap='medium')
    with left, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-composition-classes'):
        section_header('Classes bentônicas', 'Valores originais por voo; denominador preservado.', 'NASA')
        with st.container(height=70, border=False):
            st.caption('Coral · Algae · Sand | empilhamento somente quando validado')
        if b.empty:
            empty_chart('Selecione voos e classes com medidas disponíveis.')
        else:
            for unit, group in b.groupby('unit_label'):
                fig = px.bar(group, x='flight_line', y='measure', color='variable', color_discrete_map=BENTHIC,
                             barmode='stack' if valid else 'group', labels={'measure': unit, 'flight_line': 'Voo'})
                plot(fig)
        if valid:
            insight('Empilhamento validado: classes documentadas, contagens iguais ao conjunto comum válido e soma de probabilidades entre 0,95 e 1,05 em todos os pixels válidos. Valores originais, sem ajuste a 100%. Subconjuntos de classes podem não somar 100%.')
        else:
            insight('Composição de 100% não validada: medidas exibidas lado a lado. São necessários metadados de unidade e métricas de denominador comum / soma no catálogo. Não reconstruímos pixels a partir de médias.')
    with right, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-composition-ranking'):
        section_header('Ranking de coral', 'Compare as médias por voo sem interpretar tendência temporal.', 'NASA')
        with st.container(height=70, border=False):
            direction = st.radio('Ranking de coral', ['Maiores', 'Menores'], horizontal=True)
        if not coral.empty:
            ranked = coral.sort_values('measure', ascending=direction == 'Menores').head(20)
            fig = px.bar(ranked, x='measure', y='flight_line', orientation='h', text_auto='.1f', color_discrete_sequence=[BENTHIC['coral']], labels={'measure': str(coral.unit_label.iloc[0]), 'flight_line': 'Voo'})
            fig.update_yaxes(categoryorder='array', categoryarray=ranked.flight_line.tolist()[::-1])
            plot(fig)
        else:
            empty_chart('Não há médias de coral válidas na seleção.')
        insight('Até 20 voos, ordenados pelo valor médio de coral na unidade declarada. Baixos valores não comprovam mortalidade.')
    left, right = st.columns(2, gap='medium')
    with left, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-composition-scatter'):
        section_header('Coral × Algae', 'Relação entre médias por voo; sem interpretação causal.', 'NASA')
        with st.container(height=70, border=False):
            st.caption('Tooltip: voo, região e data de pesquisa')
        scatter = None
        if not b.empty and not b.duplicated(['flight_line', 'variable']).any():
            pivot = b.pivot(index='flight_line', columns='variable', values='measure').reset_index()
            if {'coral', 'algae'} <= set(pivot) and b.unit_label.nunique() == 1:
                meta = b.drop_duplicates('flight_line')
                extra = [c for c in ('region', 'observation_date') if c in meta]
                pivot = pivot.merge(meta[['flight_line'] + extra], on='flight_line', validate='one_to_one')
                scatter = px.scatter(pivot, x='coral', y='algae', hover_data=['flight_line'] + extra,
                                     color='region' if 'region' in pivot else None,
                                     labels={'coral': 'Coral · ' + b.unit_label.iloc[0], 'algae': 'Algae · ' + b.unit_label.iloc[0]})
                scatter.update_traces(marker_size=12, marker_line_width=1, marker_line_color='#FFFFFF')
        if scatter is not None:
            plot(scatter)
        else:
            empty_chart('O scatter exige Coral e Algae por voo, com unidades comparáveis e sem duplicatas ambíguas.')
        insight('Cada ponto mantém a identificação do voo e a data histórica. Não representa evolução temporal nem efeito da NOAA.')
    with right, st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-composition-distribution'):
        section_header('Distribuição de coral', 'Observações individuais quando disponíveis.', 'NASA')
        with st.container(height=70, border=False):
            st.caption('Amostra individual ou médias entre voos, identificadas abaixo')
        individual = spatial[spatial.variable == 'coral'].copy() if 'variable' in spatial else pd.DataFrame()
        if 'value' in individual:
            individual['value'] = numeric(individual.value)
            individual = individual.dropna(subset=['value'])
        if not individual.empty and 'region' in individual and 'value' in individual:
            unit = str(individual['units'].iloc[0]) if 'units' in individual else 'unidade não confirmada'
            plot(px.box(individual, x='region', y='value', points='outliers', labels={'value': 'Coral · ' + unit, 'region': 'Região'}, color_discrete_sequence=[BENTHIC['coral']]))
            insight('Distribuição das observações individuais válidas exportadas em spatial_observations.csv; possível subamostra regular, na unidade original.')
        elif not coral.empty:
            group = 'region' if 'region' in coral else 'flight_line'
            plot(px.box(coral, x=group, y='measure', points='all', labels={'measure': coral.unit_label.iloc[0]}, color_discrete_sequence=[BENTHIC['coral']]))
            insight('Distribuição de médias entre voos; não representa a distribuição de pixels.')
        else:
            empty_chart('Não há observações de coral disponíveis para esta distribuição.')
            insight('Não reconstruímos pixels a partir de estatísticas resumidas.')
    section_header('Dados bentônicos selecionados', 'Tabela completa e exportação dos valores filtrados.', 'NASA')
    table(b, 'reef_composition')


def thermal_panel(noaa, key, title):
    with st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-thermal-' + key):
        section_header(title, 'Série diária · regiões/recortes NOAA selecionados.', 'NOAA')
        with st.container(height=70, border=False):
            st.caption('Valores médios' if key.endswith('_mean') else 'Valores máximos')
        if key in noaa and noaa[key].notna().any():
            fig = px.line(noaa.sort_values('date'), x='date', y=key, color='region', markers=True,
                          labels={key: title, 'date': 'Data observada', 'region': 'Região / recorte'})
            if key.startswith('dhw'):
                fig.update_traces(fill='tozeroy')
                fig.add_hrect(y0=4, y1=8, fillcolor='#FFF06A', opacity=.04, line_width=0)
                for threshold in (4, 8):
                    fig.add_hline(y=threshold, line_dash='dash', line_color='#FFF06A' if threshold == 4 else '#FF4D2E', annotation_text=f'Referência: {threshold} °C-weeks')
            plot(fig)
            insight('DHW: referências de estresse térmico; não diagnosticam mortalidade individual.' if key.startswith('dhw') else 'Cada linha preserva seu recorte geográfico e suas datas; a janela NOAA é independente da pesquisa NASA.')
        else:
            empty_chart(f'{title}: coluna não disponível na fonte selecionada.')
            insight('Ausência de dados não equivale a ausência de estresse.')


def thermal_map(pixels):
    with st.container(height=PANEL_HEIGHT, border=True, key='cw-panel-thermal-map'):
        section_header('Mapa térmico · pixels recentes', 'Arquivo de pixels datados, quando disponível.', 'NOAA')
        available = [c for c in ('sst', 'hotspot', 'dhw') if c in pixels]
        if available:
            metric = st.selectbox('Indicador do mapa', available, format_func=lambda c: {'sst': 'SST (°C)', 'hotspot': 'HotSpot (°C)', 'dhw': 'DHW (°C-weeks)'}[c])
            map_chart(pixels, metric)
            st.caption('Fonte noaa_latest_map.csv; data(s): ' + ', '.join(pixels.date.dt.strftime('%Y-%m-%d').dropna().unique()))
        else:
            empty_chart('Mapa térmico requer noaa_latest_map.csv com coordenadas, data e medidas. Mapas globais não respondem ao filtro regional sem região explícita.')


def environmental(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    if noaa.empty:
        st.info('Séries temporais ausentes ou sem resultados no filtro; o mapa permanece disponível quando houver pixels datados.')
        thermal_map(pixels)
        return
    metrics = [('sst_mean', 'SST média (°C)'), ('anomaly_mean', 'Anomalia térmica média (°C)'),
               ('dhw_mean', 'DHW médio (°C-weeks)'), ('dhw_max', 'DHW máximo (°C-weeks)'),
               ('hotspot_mean', 'HotSpot médio (°C)')]
    for start in (0, 2):
        columns = st.columns(2, gap='medium')
        for col, (key, title) in zip(columns, metrics[start:start + 2]):
            with col:
                thermal_panel(noaa, key, title)
    columns = st.columns(2, gap='medium')
    with columns[0]:
        thermal_panel(noaa, *metrics[4])
    with columns[1]:
        thermal_map(pixels)
    section_header('Indicadores · última observação por região', 'Médias e máximos são apresentados separadamente; cada região mantém sua data.', 'NOAA')
    latest = latest_by_region(noaa)
    for start in range(0, len(latest), 3):
        rows = latest.iloc[start:start + 3]
        columns = st.columns(3, gap='medium')
        for col, (_, row) in zip(columns, rows.iterrows()):
            with col, st.container(height=250, border=True, key=f'cw-panel-region-{start}-{row.region}'):
                section_header(str(row.region), f'Data observada: {row.date:%Y-%m-%d}', 'NOAA')
                for key, title in [('dhw_mean', 'DHW médio (°C-weeks)'), ('hotspot_mean', 'HotSpot médio (°C)')]:
                    value = row.get(key)
                    st.write(f'{title}: {value:.2f}' if pd.notna(value) else f'{title}: sem dados')
                risk_pill('BAA máximo de 7 dias: ' + label(row.get('baa', float('nan'))), row.get('baa'))
    table(recent_table(latest), 'latest_environmental')
    section_header('Série temporal completa', 'Dados NOAA filtrados, preservando todas as colunas de origem.', 'NOAA')
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
    section_header('Bleaching Alert Area', 'BAA da fonte; unidades e datas preservadas.', 'NOAA')
    cols = st.columns(5, gap='medium')
    for col, (code, name) in zip(cols, ALERTS.items()):
        count = int(counts.get(code, 0)) if not alerts.empty else None
        detail = f'BAA {code} · máximo de sete dias'
        if count is not None and not regional:
            detail += f' · {100 * count / len(alerts):.1f}% dos pixels válidos'
        with col:
            alert_card(code, name, count if count is not None else '—', detail)
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
        section_header('Alertas por recorte', 'HotSpot: °C; DHW: °C-weeks. Contexto do dia, sem recalcular BAA.', 'NOAA')
        table(alerts.sort_values('baa', ascending=False, na_position='last')[cols_show], 'early_warning')
    section_header('Mapa de risco', 'BAA fornecido pela NOAA.', 'NOAA')
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


def render_page(index):
    bundle, cat, b, full, spatial, noaa, pixels = st.session_state['_cw_context']
    if index == 0:
        observed = noaa if not noaa.empty else pixels
        date = f'{observed.date.max():%Y-%m-%d}' if not observed.empty and 'date' in observed else 'indisponível'
        hero('CoralWatch', 'Reef Health & Thermal Stress Monitor · Última observação NOAA: ' + date)
    else:
        hero(PAGES[index], 'Observações científicas, contexto e fontes preservados.')
    st.info(NOTICE)
    st.caption(f'Fonte NOAA temporal: {bundle["source"]}' + (' (indisponível ou sem observações válidas).' if bundle['noaa'].empty else '.') + ' NASA: flight_catalog.csv e benthic_variable_summary.csv; fallback integrado informado na metodologia.')
    if not bundle['raw']:
        st.warning('Nenhum CSV disponível em data/processed/. Coloque os arquivos processados nessa pasta. Nenhum dado fictício é gerado.')
    if index == 0:
        overview(bundle, cat, b, full, spatial, noaa, pixels)
    elif index == 1:
        composition(bundle, cat, b, full, spatial)
    elif index == 2:
        environmental(bundle, noaa, pixels)
    else:
        warning_page(bundle, noaa, pixels)
    disclaimer()
    methodology(bundle)


def main():
    apply_theme()
    st.sidebar.title('🪸 CoralWatch')
    st.sidebar.caption('Reef Health & Thermal Stress Monitor')
    paths = ['1_Overview.py', '2_Reef_Composition.py', '3_Environmental_Monitoring.py', '4_Early_Warning.py']
    page_dir = Path(__file__).resolve().parents[1] / 'pages'
    navigation = st.navigation([st.Page(page_dir / path, title=title) for path, title in zip(paths, PAGES)])
    if st.sidebar.button('Atualizar cache', width='stretch'):
        st.cache_data.clear()
    bundle = load_bundle()
    # Presentation accessors reuse the existing cached loader, without processing.
    nasa, noaa = load_nasa(bundle), load_noaa(bundle)
    filtered = render_filters({**bundle, **nasa, **noaa})
    st.session_state['_cw_context'] = (bundle, *filtered)
    navigation.run()
