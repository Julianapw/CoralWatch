"""Portuguese, source-aware presentation; scientific adapters remain unchanged."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dashboard.data import latest_by_region, composition_valid, coordinates, numeric
from dashboard.charts import plot, map_chart, bounds_points, BENTHIC, ALERTS, label
from core.components import (kpi_card, alert_card, section_header, disclaimer, hero,
                             insight, empty_chart, risk_pill, area_labels, display_name, display_frame)
from core.data import load_bundle, load_nasa, load_noaa
from core.filters import render_filters
from core.theme import apply_theme

PAGES = ['Visão geral', 'Composição dos recifes', 'Monitoramento térmico', 'Alertas de branqueamento']
NOTICE = ('NASA CORAL apresenta observações históricas. NOAA fornece indicadores de estresse térmico e risco de branqueamento na data informada. Esses dados não diagnosticam mortalidade individual de corais.')


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
        st.caption('Fonte temporal selecionada: ' + bundle['source'] + (' (sem observações válidas)' if bundle['noaa'].empty else ''))
        st.write('Os nomes Área 01, Área 02 etc. vêm do catálogo NASA completo, ordenado por data e código do voo antes dos filtros. Cada área é o recorte de um voo, não necessariamente um recife. Os códigos NASA e NOAA não são associados por esse nome de apresentação.')
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





def source_period(d, source, date_column):
    if date_column not in d or d[date_column].dropna().empty:
        return f'{source} · período indisponível'
    return f'{source} · {d[date_column].min():%d/%m/%Y} a {d[date_column].max():%d/%m/%Y}'


def thermal_status(latest, inline=False):
    """Use the latest rows already selected by the existing scientific helper."""
    if latest.empty:
        empty_chart('Nenhum recorte NOAA com observação no filtro selecionado.')
        return
    columns = st.columns(3, gap='medium') if inline else None
    for index, (_, row) in enumerate(latest.iterrows()):
        with (columns[index % 3] if columns else st.container()):
            st.markdown('**' + str(row.region) + '**')
            risk_pill(label(row.get('baa', float('nan'))), row.get('baa'))
            st.caption(f'Observado em {row.date:%d/%m/%Y} · BAA máximo de sete dias')
    st.caption('Identificadores NOAA preservados: não há nova correspondência com os voos NASA.')


def overview(bundle, cat, b, full, spatial, noaa, pixels):
    latest = latest_by_region(noaa)
    regions = cat['region'].nunique() if 'region' in cat else (full.region.nunique() if 'region' in full else 0)
    flights = cat['flight_line'].nunique() if 'flight_line' in cat else (b.flight_line.nunique() if 'flight_line' in b else 0)
    coral = full[full.variable == 'coral'] if 'variable' in full else pd.DataFrame()
    compatible = not coral.empty and coral.unit_label.nunique() == 1
    value = coral.measure.mean() if compatible else float('nan')
    baa = noaa[noaa.date == noaa.date.max()].baa.max() if not noaa.empty and 'baa' in noaa else (pixels.baa.max() if not pixels.empty and 'baa' in pixels else float('nan'))
    if 'region' in cat:
        st.write('Região pesquisada: ' + ' · '.join(str(v) for v in cat.region.dropna().unique()))
    cols = st.columns(4, gap='medium')
    with cols[0]:
        kpi_card('Regiões geográficas', regions if regions else '—', 'Rótulos regionais do catálogo NASA.', 'regions')
    with cols[1]:
        kpi_card('Áreas / voos', flights, 'Cada área representa o recorte de um voo.', 'flights')
    with cols[2]:
        kpi_card('Coral · média entre voos', f'{value:.1f}' if pd.notna(value) else '—', str(coral.unit_label.iloc[0]) if compatible else 'Unidade comparável indisponível.', 'coral')
    with cols[3]:
        kpi_card('Maior BAA · última data', label(baa), 'NOAA · máximo de sete dias da fonte.', 'alert-max', 'NOAA')
    st.caption(source_period(cat, 'NASA CORAL histórica', 'observation_date'))
    freshness(noaa if not noaa.empty else pixels)
    st.caption('“Área” é o recorte de um voo, não necessariamente um recife individual. A média de coral é não ponderada entre voos; não representa cobertura de toda a região.')
    layer = st.radio('Camada do mapa', ['NASA histórica', 'NOAA recente'], horizontal=True)
    left, right = st.columns([2.2, 1], gap='large')
    with left:
        section_header('Áreas pesquisadas' if layer == 'NASA histórica' else 'Pixels NOAA recentes')
        if layer == 'NASA histórica':
            points = spatial[spatial.variable == 'coral'].copy() if 'variable' in spatial else spatial
            st.caption(source_period(cat, 'NASA CORAL', 'observation_date'))
            if not coordinates(points).empty:
                map_chart(display_frame(points), 'value' if 'value' in points else None)
                st.caption('Probabilidade de coral na unidade original; observações individuais exportadas por amostragem regular.')
            elif not coordinates(spatial).empty:
                map_chart(display_frame(spatial))
                st.caption('Observações individuais NASA; possível amostragem regular.')
            else:
                map_chart(display_frame(bounds_points(cat)))
                st.caption('Centroides aproximados dos limites de cada voo; não são pixels observados.')
        else:
            map_chart(pixels, 'baa', True)
            if not pixels.empty:
                st.caption(f'NOAA · pixels observados em {pixels.date.max():%d/%m/%Y} · BAA máximo de sete dias.')
    with right:
        section_header('Situação térmica por recorte')
        thermal_status(latest)
    section_header('Composição histórica', 'NASA CORAL · médias por voo na unidade declarada.')
    if b.empty:
        st.info('Sem medidas bentônicas no filtro. Verifique benthic_variable_summary.csv e os metadados de unidade.')
    else:
        groups = list(b.groupby('unit_label'))
        for unit, group in groups:
            view = display_frame(group)
            fig = px.bar(view, x='_area', y='measure', color='variable', color_discrete_map=BENTHIC,
                         barmode='group', hover_data=[c for c in ('flight_line', 'source_file', 'observation_date') if c in view],
                         labels={'_area': 'Área pesquisada', 'measure': unit, 'variable': 'Classe bentônica'})
            plot(fig)
    with st.expander('Ver dados e exportar'):
        st.write('NASA · resumo bentônico completo')
        table(b, 'overview_nasa')
        st.write('NOAA · última observação por região / recorte')
        if not latest.empty:
            table(recent_table(latest), 'overview_noaa')


def composition(bundle, cat, b, full, spatial):
    st.caption(source_period(cat, 'NASA CORAL', 'observation_date'))
    st.caption('Coral, algas e areia são probabilidades de classe. A porcentagem, quando validada nos metadados, expressa probabilidade média; não medição direta de área.')
    if b.empty:
        st.info('Sem medidas bentônicas neste filtro. Selecione voos e classes ou verifique benthic_variable_summary.csv.')
    valid = composition_valid(full, cat)
    coral = b[b.variable == 'coral'].dropna(subset=['measure']) if 'variable' in b else pd.DataFrame()
    direction = st.radio('Ordenar ranking de coral', ['Maiores', 'Menores'], horizontal=True)
    left, right = st.columns([1.2, 1], gap='large')
    with left:
        section_header('Composição por área', 'Médias por voo · denominador original preservado.')
        if b.empty:
            empty_chart('Selecione voos e classes com medidas disponíveis.')
        else:
            for unit, group in b.groupby('unit_label'):
                view = display_frame(group)
                plot(px.bar(view, x='_area', y='measure', color='variable', color_discrete_map=BENTHIC,
                            barmode='stack' if valid else 'group', hover_data=[c for c in ('flight_line', 'source_file', 'observation_date') if c in view],
                            labels={'measure': unit, '_area': 'Área pesquisada', 'variable': 'Classe bentônica'}))
        insight('Classes compatíveis com denominador comum; valores originais, sem renormalização. O subconjunto pode não somar 100%.' if valid else 'Empilhamento não validado: medidas lado a lado. Não reconstruímos pixels nem ajustamos a soma a 100%.')
    with right:
        section_header('Ranking de coral', 'Até 20 médias por voo · mesma unidade do resumo bentônico.')
        if not coral.empty:
            ranked = display_frame(coral.sort_values('measure', ascending=direction == 'Menores').head(20))
            fig = px.bar(ranked, x='measure', y='_area', orientation='h', text_auto='.1f', color_discrete_sequence=[BENTHIC['coral']],
                         hover_data=[c for c in ('flight_line', 'source_file', 'observation_date') if c in ranked],
                         labels={'measure': str(coral.unit_label.iloc[0]), '_area': 'Área pesquisada'})
            fig.update_yaxes(categoryorder='array', categoryarray=ranked._area.tolist()[::-1])
            plot(fig)
        else:
            empty_chart('Não há médias válidas de coral na seleção.')
        insight('Comparação histórica entre voos; baixos valores não comprovam mortalidade.')
    st.divider()
    section_header('Explorar as observações', 'NASA CORAL · associação entre medidas e distribuição dos valores históricos.')
    left, right = st.columns(2, gap='large')
    with left:
        st.markdown('**Coral × algas**')
        scatter = None
        if not b.empty and not b.duplicated(['flight_line', 'variable']).any():
            pivot = b.pivot(index='flight_line', columns='variable', values='measure').reset_index()
            if {'coral', 'algae'} <= set(pivot) and b.unit_label.nunique() == 1:
                meta = b.drop_duplicates('flight_line')
                extra = [c for c in ('region', 'observation_date', 'source_file') if c in meta]
                pivot = display_frame(pivot.merge(meta[['flight_line'] + extra], on='flight_line', validate='one_to_one'))
                scatter = px.scatter(pivot, x='coral', y='algae', hover_name='_area', hover_data=['flight_line'] + extra,
                                     color='region' if 'region' in pivot else None,
                                     labels={'coral': 'Coral · ' + b.unit_label.iloc[0], 'algae': 'Algas · ' + b.unit_label.iloc[0], 'region': 'Região', '_area': 'Área'})
                scatter.update_traces(marker_size=12, marker_line_width=1, marker_line_color='#FFFFFF')
        if scatter is not None:
            plot(scatter)
        else:
            empty_chart('São necessárias médias de Coral e Algae com unidades comparáveis e sem duplicatas ambíguas.')
        insight('Cada ponto é um voo histórico; não indica tendência temporal nem relação causal com a NOAA.')
    with right:
        st.markdown('**Distribuição de coral**')
        individual = spatial[spatial.variable == 'coral'].copy() if 'variable' in spatial else pd.DataFrame()
        if 'value' in individual:
            individual['value'] = numeric(individual.value)
            individual = individual.dropna(subset=['value'])
        if not individual.empty and 'region' in individual and 'value' in individual:
            unit = str(individual['units'].iloc[0]) if 'units' in individual else 'unidade não confirmada'
            view = display_frame(individual)
            group = '_area' if individual.region.nunique() == 1 and '_area' in view else 'region'
            plot(px.box(view, x=group, y='value', points='outliers', hover_data=[c for c in ('flight_line', 'source_file') if c in view],
                        labels={'value': 'Coral · ' + unit, 'region': 'Região', '_area': 'Área pesquisada'}, color_discrete_sequence=[BENTHIC['coral']]))
            insight('Observações individuais válidas exportadas; possível subamostra regular, na unidade original. Agrupamento por voo quando há uma única região.')
        elif not coral.empty:
            view = display_frame(coral)
            group = 'region' if 'region' in coral and coral.region.nunique() > 1 else '_area'
            plot(px.box(view, x=group, y='measure', points='all', hover_data=[c for c in ('flight_line', 'source_file') if c in view], labels={'measure': coral.unit_label.iloc[0], '_area': 'Área pesquisada', 'region': 'Região'}, color_discrete_sequence=[BENTHIC['coral']]))
            insight('Distribuição de médias entre voos; não representa a distribuição de pixels.')
        else:
            empty_chart('Não há observações de coral disponíveis para esta distribuição.')
    with st.expander('Ver dados e exportar'):
        table(b, 'reef_composition')


def thermal_panel(noaa, key, title):
    section_header(title, source_period(noaa, 'NOAA · série diária', 'date'), 'NOAA')
    if key in noaa and noaa[key].notna().any():
        fig = px.line(noaa.sort_values('date'), x='date', y=key, color='region', markers=True,
                      labels={key: title, 'date': 'Data observada', 'region': 'Região / recorte'})
        fig.update_xaxes(tickformat='%d/%m/%Y')
        if key.startswith('dhw'):
            fig.update_traces(fill='tozeroy')
            fig.add_hrect(y0=4, y1=8, fillcolor='#FFF06A', opacity=.04, line_width=0)
            for threshold in (4, 8):
                fig.add_hline(y=threshold, line_dash='dash', line_color='#967500' if threshold == 4 else '#BF321B', annotation_text=f'Referência: {threshold} °C-weeks')
        plot(fig)
    else:
        empty_chart(f'{title}: coluna não disponível na fonte selecionada.')


def thermal_map(pixels):
    section_header('Mapa térmico', 'NOAA · pixels da última data exportada, quando disponíveis.', 'NOAA')
    available = [c for c in ('sst', 'hotspot', 'dhw') if c in pixels]
    if available:
        metric = st.selectbox('Indicador do mapa', available, format_func=lambda c: {'sst': 'SST (°C)', 'hotspot': 'HotSpot (°C)', 'dhw': 'DHW (°C-weeks)'}[c])
        map_chart(pixels, metric)
        st.caption('Data observada: ' + ', '.join(pixels.date.dt.strftime('%d/%m/%Y').dropna().unique()))
    else:
        empty_chart('Não há pixels térmicos compatíveis no filtro. O mapa requer noaa_latest_map.csv com coordenadas, data e medidas; dados globais não respondem a um filtro regional sem identificação explícita.')


def environmental(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    if noaa.empty:
        st.info('Sem séries temporais no filtro. O mapa permanece disponível quando houver pixels datados.')
        thermal_map(pixels)
        return
    thermal_panel(noaa, 'sst_mean', 'Temperatura da superfície do mar · SST média (°C)')
    left, right = st.columns(2, gap='large')
    with left:
        thermal_panel(noaa, 'dhw_mean', 'DHW médio (°C-weeks)')
    with right:
        thermal_panel(noaa, 'dhw_max', 'DHW máximo (°C-weeks)')
    st.caption('As referências de 4 e 8 °C-weeks indicam estresse térmico acumulado, não diagnóstico de mortalidade individual.')
    with st.expander('Anomalia térmica e HotSpot', expanded=False):
        thermal_panel(noaa, 'anomaly_mean', 'Anomalia térmica média (°C)')
        thermal_panel(noaa, 'hotspot_mean', 'HotSpot médio (°C)')
    section_header('Última observação por recorte', 'NOAA · médias e máximos separados; cada recorte conserva sua data.', 'NOAA')
    latest = latest_by_region(noaa)
    st.dataframe(recent_table(latest), hide_index=True, width='stretch')
    thermal_map(pixels)
    with st.expander('Ver dados e exportar'):
        st.write('Última observação por região / recorte')
        table(recent_table(latest), 'latest_environmental')
        st.write('Série temporal completa · todas as colunas de origem')
        table(noaa, 'environmental_timeseries')


def warning_page(bundle, noaa, pixels):
    freshness(noaa if not noaa.empty else pixels)
    latest = latest_by_region(noaa)
    regional = bundle['regional'] and not latest.empty and 'baa' in latest
    if regional:
        alerts = latest.copy()
        counts = alerts.baa.value_counts()
        st.caption(f'{len(alerts)} regiões/recortes NOAA identificados · última data de cada recorte no filtro · BAA máximo de sete dias da fonte.')
    elif not pixels.empty and 'baa' in pixels:
        alerts = pixels[pixels.baa.notna()].copy()
        counts = alerts.baa.value_counts()
        st.caption(f'Denominador: {len(alerts)} pixels oceânicos com BAA válido, não recifes afetados. Data: {pixels.date.max():%d/%m/%Y}.')
    else:
        alerts, counts = pd.DataFrame(), pd.Series(dtype=float)
        st.info('Sem classificação regional ou pixels BAA datados. Ausência de dados não equivale a No Stress.')
        if not latest.empty and 'baa' in latest:
            st.write('BAA do recorte global: ' + label(latest.baa.iloc[0]))
        summary = bundle['raw'].get('noaa_alert_summary.csv', pd.DataFrame())
        if not summary.empty:
            with st.expander('Resumo BAA original'):
                st.caption('Sem mapa datado, este resumo não é usado para contagens atuais.')
                st.dataframe(summary)
    section_header('Situação por recorte', 'Classificação NOAA fornecida pela fonte, sem recálculo.', 'NOAA')
    if regional:
        thermal_status(latest.sort_values('baa', ascending=False, na_position='last'), inline=True)
    st.caption('HotSpot: °C; DHW: °C-weeks. Os indicadores do dia são contexto, não uma reconstituição do BAA máximo de sete dias.')
    if not alerts.empty:
        extra = alerts[alerts.baa.notna() & ~alerts.baa.isin(ALERTS)]
        if not extra.empty:
            st.warning('Códigos adicionais preservados: ' + ', '.join(str(x) for x in extra.baa.unique()) + '. Consulte noaa_config.json / metadados da fonte.')
        alerts['Nível'] = alerts.baa.map(label)
        alerts['Interpretação'] = 'BAA fornecido pela fonte (máximo de 7 dias); HotSpot/DHW do dia são apenas contexto.'
        cols_show = [c for c in ('region', 'latitude', 'longitude', 'date', 'baa', 'Nível', 'hotspot_mean', 'hotspot_max', 'dhw_mean', 'dhw_max', 'hotspot', 'dhw', 'Interpretação') if c in alerts]
        context_cols = [c for c in cols_show if c not in ('Interpretação', 'latitude', 'longitude')]
        st.dataframe(alerts.sort_values('baa', ascending=False, na_position='last')[context_cols].rename(columns={
            'region': 'Recorte NOAA', 'date': 'Data observada', 'baa': 'Código BAA', 'hotspot_mean': 'HotSpot médio (°C)',
            'hotspot_max': 'HotSpot máximo (°C)', 'dhw_mean': 'DHW médio (°C-weeks)', 'dhw_max': 'DHW máximo (°C-weeks)',
            'hotspot': 'HotSpot do pixel (°C)', 'dhw': 'DHW do pixel (°C-weeks)'}), hide_index=True, width='stretch')
    if regional:
        missing = int(latest.baa.isna().sum())
        if missing:
            st.warning(f'{missing} região(ões) sem classificação; excluídas das cinco categorias.')
    with st.expander('Níveis BAA e contagens', expanded=False):
        descriptions = {0: 'Sem estresse indicado pela classificação', 1: 'Vigilância para branqueamento', 2: 'Aviso de branqueamento', 3: 'Alerta de nível 1', 4: 'Alerta de nível 2'}
        for code, name in ALERTS.items():
            count = int(counts.get(code, 0)) if not alerts.empty else None
            detail = descriptions[code] + ' · ' + ('regiões/recortes' if regional else 'pixels oceânicos válidos')
            if count is not None and not regional:
                detail += f' · {100 * count / len(alerts):.1f}% dos pixels válidos'
            alert_card(code, name, count if count is not None else '—', detail)
    section_header('Mapa de alertas', 'NOAA · BAA máximo de sete dias; cada observação mantém sua data.', 'NOAA')
    if not pixels.empty:
        map_chart(pixels, 'baa', True)
    elif regional:
        geometry = bundle['raw'].get('noaa_spatial_summary.csv', pd.DataFrame())
        if 'region' in geometry and not geometry.region.duplicated().any():
            bounds = [c for c in ('latitude_min', 'latitude_max', 'longitude_min', 'longitude_max') if c in geometry]
            mapped = latest.merge(geometry[['region'] + bounds], on='region', how='left', validate='one_to_one')
            map_chart(bounds_points(mapped), 'baa', True)
            st.caption('Centroides aproximados dos limites regionais. Classificação e data vêm do resumo diário; as estatísticas históricas do período não são usadas como alerta atual.')
        else:
            empty_chart('São necessários pixels datados ou limites regionais compatíveis com o resumo diário.')
    else:
        empty_chart('Nenhuma geometria compatível com a classificação disponível.')
    with st.expander('Ver dados e exportar'):
        if not alerts.empty:
            table(alerts.sort_values('baa', ascending=False, na_position='last')[cols_show], 'early_warning')
        if noaa.empty:
            for name in ('noaa_spatial_summary.csv', 'integrated_regional_summary.csv'):
                historical = bundle['raw'].get(name, pd.DataFrame())
                if not historical.empty:
                    st.warning(f'{name}: resumo histórico de todo o intervalo; não é alerta atual.')
                    table(historical, 'historical_' + name)


def render_page(index):
    bundle, cat, b, full, spatial, noaa, pixels = st.session_state['_cw_context']
    hero('CoralWatch' if index == 0 else PAGES[index], 'Composição histórica dos recifes e contexto térmico recente')
    if not bundle['raw']:
        st.info('Sem CSVs em data/processed/. Coloque os arquivos processados nessa pasta; a interface não gera dados fictícios.')
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
    st.sidebar.title('CoralWatch')
    st.sidebar.caption('Composição histórica dos recifes e contexto térmico recente')
    paths = ['1_Overview.py', '2_Reef_Composition.py', '3_Environmental_Monitoring.py', '4_Early_Warning.py']
    page_dir = Path(__file__).resolve().parents[1] / 'pages'
    navigation = st.navigation([st.Page(page_dir / path, title=title) for path, title in zip(paths, PAGES)])
    if st.sidebar.button('Atualizar dados em cache', width='stretch'):
        st.cache_data.clear()
    bundle = load_bundle()
    st.session_state['_cw_area_labels'] = area_labels(bundle['catalog'])
    nasa, noaa = load_nasa(bundle), load_noaa(bundle)
    filtered = render_filters({**bundle, **nasa, **noaa})
    st.session_state['_cw_context'] = (bundle, *filtered)
    navigation.run()
