# CoralWatch — preparação de dados no VS Code

Projeto Python tradicional (sem Jupyter/Colab) para preparar os dados do **NASA CORAL / PRISM L2-RBEN** e os indicadores térmicos do **NOAA Coral Reef Watch v3.1**. O resultado é um conjunto de CSVs/JSONs e um ZIP para a pessoa que vai construir o Streamlit.

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

Não coloque nada manualmente. Essa pasta será preenchida pelo programa com os dados prontos para o Streamlit. Se quiser reprocessar tudo, pode apagar os arquivos gerados daqui e executar de novo.

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
