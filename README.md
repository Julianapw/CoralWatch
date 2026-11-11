# CoralWatch — preparação de dados e dashboard Streamlit

Projeto Python para preparar e explorar os dados do **NASA CORAL / PRISM L2-RBEN** e os indicadores térmicos do **NOAA Coral Reef Watch v3.1**. O pipeline gera CSVs/JSONs e um ZIP; o dashboard Streamlit lê esses produtos em quatro páginas.

## 1. Estrutura das pastas

```text
CoralWatch_VSCode/
├── .vscode/
│   └── extensions.json
├── coralwatch/
│   ├── __init__.py
│   ├── settings.py
│   ├── nasa.py
│   ├── noaa.py
│   └── pipeline.py
├── data/
│   ├── raw/
│   │   ├── nasa/          # coloque aqui os NetCDF .nc/.nc4/.cdf baixados da NASA
│   │   └── noaa/          # o script salva aqui o NetCDF baixado da NOAA
│   └── processed/        # o script gera aqui CSVs e JSONs para o dashboard
├── downloads/            # o script gera aqui coralwatch_dashboard_data.zip
├── logs/                 # reservado para logs
├── run_pipeline.py       # arquivo que você executa
├── requirements.txt
├── .gitignore
└── README.md
```

## 2. O que você precisa colocar manualmente

### `data/raw/nasa/`

Coloque aqui os arquivos **NetCDF do produto NASA CORAL PRISM Benthic Cover, Level 2 / RBEN** (`.nc`, `.nc4` ou `.cdf`). Para o primeiro teste, baixe de 3 a 10 arquivos da mesma região.

- Navegador: https://oceandata.sci.gsfc.nasa.gov/coral_browser/
- Selecione a região e os voos desejados.
- Baixe o produto **L2**. Não comece com L1/reflectância bruta.
- Copie os arquivos baixados para `data/raw/nasa/`.

**Não** coloque PDF, imagem, CSV aleatório ou os arquivos do dashboard nessa pasta.

### `data/raw/noaa/`

Não precisa colocar nada para o fluxo normal. O programa baixa automaticamente o recorte NOAA e guarda o NetCDF nessa pasta. Se você já tiver um NetCDF NOAA, pode usar `--noaa-file caminho/do/arquivo.nc`.

### `data/processed/`

Essa pasta será preenchida pelo pipeline com os dados prontos para o Streamlit. Para usar produtos já preparados, copie os CSVs/JSONs existentes para essa pasta, conforme a seção **Dashboard Streamlit** abaixo.

### `downloads/`

Não coloque nada manualmente. O ZIP para sua amiga será criado aqui: `coralwatch_dashboard_data.zip`.

## 3. Configuração antes de executar

Abra `coralwatch/settings.py` e confira estas configurações:

```python
REGION_NAME = "Great Barrier Reef"
NOAA_DAYS = 30
NOAA_MAP_STRIDE = 1
```

Se baixou outra região, altere `REGION_NAME`. O pipeline tenta obter os limites geográficos a partir dos NetCDF NASA. Se os arquivos não trouxerem latitude/longitude reconhecíveis, será usada `NOAA_BBOX_FALLBACK`, que por padrão corresponde à Great Barrier Reef. Nesse caso, atualize também os quatro limites (`lat_min`, `lat_max`, `lon_min`, `lon_max`) para a região escolhida.

`NOAA_DAYS = 30` consulta os últimos 30 dias disponíveis. Para 90 dias, altere para `90`.

## 4. Abrir e preparar no VS Code

1. Extraia a pasta `CoralWatch_VSCode`.
2. No VS Code, clique em **File > Open Folder** e abra essa pasta.
3. Abra **Terminal > New Terminal**.
4. Confirme que está usando Python 3.10 ou superior e crie/ative um ambiente virtual.

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

5. Coloque os NetCDF NASA em `data/raw/nasa/`.
6. No terminal, com o ambiente virtual ativado, execute:

```bash
python run_pipeline.py
```

O programa executa NASA primeiro, depois consulta NOAA e cria `downloads/coralwatch_dashboard_data.zip`.

## 5. Executar somente uma fonte

Processar apenas os arquivos NASA:

```bash
python run_pipeline.py --source nasa
```

Processar apenas NOAA (se `flight_catalog.csv` existir, usa a área derivada da NASA; caso contrário, usa o fallback de `settings.py`):

```bash
python run_pipeline.py --source noaa
```

## 6. Arquivos entregues ao Streamlit

Os resultados ficam em `data/processed/`:

**NASA CORAL:**
- `flight_catalog.csv`
- `flight_inventory.csv`
- `variable_inventory.csv`
- `benthic_variable_summary.csv`
- `spatial_observations.csv`
- `class_legend.csv`
- `dashboard_config.json`

**NOAA Coral Reef Watch:**
- `noaa_thermal_timeseries.csv`
- `noaa_latest_map.csv`
- `noaa_alert_summary.csv`
- `noaa_config.json`

Depois, envie para sua amiga o arquivo `downloads/coralwatch_dashboard_data.zip` e o documento `STREAMLIT_HANDOFF.md` (incluído no pacote, fora da pasta principal).

## 7. Observações científicas

- NASA CORAL é uma campanha histórica (principalmente 2016–2017): não descreve a saúde atual do recife.
- NOAA Coral Reef Watch v3.1 fornece indicadores de estresse térmico e risco de branqueamento, não diagnóstico de mortalidade de uma colônia.
- `pixel_percent` é calculado sobre pixels oceânicos válidos no recorte geográfico, não sobre corais ou área total de recife.
- DHW de 4 e 8 °C-weeks são referências de estresse térmico usadas no contexto NOAA; interpretar como risco regional, não certeza de morte.
- As variáveis bentônicas são detectadas por nome/descrição e seus metadados são preservados. Não presumimos que todo campo seja porcentagem de coral.

## Fontes

- NASA CORAL-PRISM Browser: https://oceandata.sci.gsfc.nasa.gov/coral_browser/
- NASA CORAL L2/RBEN DOI: https://doi.org/10.5067/PRISM/CORAL/L2/RBEN/V1
- NOAA Coral Reef Watch v3.1: https://coralreefwatch.noaa.gov/product/5km/index.php
- PacIOOS ERDDAP dataset: https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km.html

## Dashboard Streamlit

O dashboard tem quatro páginas: **Overview**, **Reef Composition (NASA CORAL)**,
**Environmental Monitoring (NOAA)** e **Early Warning System**. Metodologia e fontes
ficam em um expander em cada página. A interface somente lê os arquivos processados:
abrir o dashboard não executa downloads, NetCDF ou o pipeline.

No Windows PowerShell, a partir da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Não é necessário ativar o ambiente nem alterar a política de execução do PowerShell.
Os caminhos dos dados são resolvidos em relação aos arquivos Python, independentemente
do diretório de execução. Se executar fora do repositório, informe o caminho absoluto
para `app.py` no comando Streamlit.

### Colocar dados existentes no dashboard

Copie os CSVs/JSONs já processados para **data/processed/** (ou extraia a pasta
`processed/` do ZIP do projeto para esse destino). Não coloque NetCDF nessa pasta.
Também é possível gerar esses produtos separadamente com as ferramentas de preparação
descritas acima. Não é necessário ter as duas fontes para navegar.

- NASA: `flight_catalog.csv`, `benthic_variable_summary.csv`, `spatial_observations.csv`,
  `variable_inventory.csv`, `class_legend.csv`, `dashboard_config.json` e, opcionalmente,
  `nasa_pixel_quality.csv`.
- NOAA regional: `noaa_daily_summary.csv`. `noaa_spatial_summary.csv` pode fornecer
  os limites regionais para o mapa, mas suas estatísticas são históricas do intervalo.
- NOAA original: `noaa_thermal_timeseries.csv`, `noaa_latest_map.csv`,
  `noaa_alert_summary.csv`, `noaa_config.json`.
- `integrated_regional_summary.csv` fornece fallback para catálogo/médias NASA;
  unidades precisam ser confirmadas pelos metadados. Seus máximos NOAA nunca
  alimentam indicadores atuais.

A série regional diária tem prioridade sobre a original; os formatos equivalentes
não são concatenados. Cada região usa sua última data dentro do intervalo selecionado.
Os filtros NASA e NOAA são independentes. Mapas globais de pixels não respondem a um
filtro regional sem identificador regional explícito. Cada mapa preserva sua data;
sem data no CSV, o mapa exige `latest_date` ou `latest_observation_date` no JSON NOAA.

O cache acompanha tamanho e data de modificação dos arquivos. Use **Atualizar cache**
para forçar uma nova leitura. Cada tabela principal permite baixar o CSV filtrado.
Arquivos ausentes, vazios e esquemas incompatíveis produzem mensagens sem dados fictícios.
Detalhes de leitura ficam em **Metodologia e fontes**.

As camadas coral/algae/sand do produtor são probabilidades. A conversão para porcentagem
exige evidência explícita de escala 0–1 nos metadados, nunca apenas valores pequenos.
As barras são agrupadas por padrão. O empilhamento exige as três classes, contagens
compatíveis com o denominador comum e métricas de soma por pixel no catálogo, dentro
de 0,95–1,05. Mesmo assim não há renormalização a 100%. O card de coral representa
média não ponderada das médias entre voos, não cobertura de toda a área.

BAA é a classificação fornecida pela fonte (máximo de sete dias), sem recálculo por
médias de HotSpot/DHW. Códigos extras são preservados. Os cinco cards usam regiões
quando disponíveis; no formato de pixels, o denominador são pixels oceânicos com BAA
válido no arquivo exportado. Dados NOAA com mais de sete dias recebem aviso de idade.
Os mapas usam um fundo cartográfico externo; sua renderização depende da conexão do navegador.

### Validação

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes usam diretórios temporários, sem escrever fixtures em `data/processed/`.
Cobrem os dois formatos NOAA, datas diferentes entre regiões, ausência de fontes,
arquivos vazios, unidades, coordenadas inválidas, códigos BAA extras, invalidação do
cache e isolamento dos máximos históricos. O Streamlit AppTest abre as quatro páginas
com fontes isoladas, combinadas e filtros vazios. AppTest valida execução e widgets;
não substitui uma inspeção visual em navegador ou uma validação científica dos dados reais.

### Interface e organização visual

A navegação usa `st.navigation`, com as quatro entradas em `pages/`. O tema claro,
as cores e as dimensões ficam em `core/theme.py`; os componentes reutilizáveis em
`core/components.py` e os filtros compartilhados em `core/filters.py`. A fachada
`core/data.py` reutiliza o carregador científico existente de `dashboard/data.py`.

As quatro páginas usam títulos e eixos em português, indicadores compactos e painéis
com altura natural, sem rolagem interna para acomodar textos. A visão geral prioriza
o mapa; as séries SST e DHW têm destaque no monitoramento térmico. Zoom e exportação
de imagem do Plotly permanecem disponíveis. Tabelas completas e downloads ficam em
“Ver dados e exportar”; os detalhes científicos em “Metodologia e fontes”.

Nomes como “Área 01 · voo de 08/09/2016” são derivados do catálogo NASA completo,
antes dos filtros, apenas para apresentação. Os identificadores originais permanecem
nos tooltips, tabelas e downloads. Nenhuma nova relação entre NASA e NOAA é criada.
