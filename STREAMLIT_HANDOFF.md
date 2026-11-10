# CoralWatch — contrato de dados para o Streamlit

O pipeline Python entrega os CSVs/JSONs dentro de `processed/` no arquivo `downloads/coralwatch_dashboard_data.zip`. O dashboard deve consumir esses arquivos; não precisa abrir os NetCDF brutos.

## Fontes e separação temporal

1. **NASA CORAL/PRISM L2/RBEN:** observações históricas da campanha CORAL (principalmente 2016–2017), para explorar variáveis bentônicas e metadados dos NetCDF.
2. **NOAA Coral Reef Watch v3.1:** produto diário global de satélite com resolução aproximada de 5 km, para contexto recente de estresse térmico e alertas de branqueamento.

Não misturar as datas para sugerir que a campanha NASA mede a condição atual. NOAA fornece indicadores de risco térmico; não confirma que uma colônia específica esteja morta.

## Arquivos e uso sugerido

| Arquivo | Uso |
|---|---|
| `flight_catalog.csv` | Catálogo de voos, região, datas e limites geográficos. |
| `flight_inventory.csv` | Metadados técnicos por arquivo. |
| `variable_inventory.csv` | Dicionário: nome, unidades, descrição, dimensões, flags e intervalo amostrado. |
| `benthic_variable_summary.csv` | Estatísticas amostradas das variáveis com nomes/descrições relacionados a coral, algas, substrato, cobertura etc. |
| `spatial_observations.csv` | Observações georreferenciadas em formato longo; pode estar vazio se o NetCDF não tiver coordenadas compatíveis. |
| `class_legend.csv` | `flag_values` e `flag_meanings` que existirem nos metadados. Pode estar vazio. |
| `dashboard_config.json` | Fonte NASA, DOI, região e nota histórica. |
| `noaa_thermal_timeseries.csv` | Série diária de médias, medianas, máximos de DHW, HotSpot, SST, anomalia SST e distribuição BAA. |
| `noaa_latest_map.csv` | Pixels do último dia: latitude, longitude, BAA, DHW, HotSpot, SST e anomalia SST. |
| `noaa_alert_summary.csv` | Quantidade e percentual de pixels oceânicos válidos por nível BAA no último dia. |
| `noaa_config.json` | Fonte NOAA, versão, período, data mais recente, bounding box, legenda e limitações. |

## Carregamento no Streamlit

```python
from pathlib import Path
import json
import pandas as pd

DATA_DIR = Path("data/processed")

flight_catalog = pd.read_csv(DATA_DIR / "flight_catalog.csv")
flight_inventory = pd.read_csv(DATA_DIR / "flight_inventory.csv")
variable_inventory = pd.read_csv(DATA_DIR / "variable_inventory.csv")
benthic_summary = pd.read_csv(DATA_DIR / "benthic_variable_summary.csv")
spatial_observations = pd.read_csv(DATA_DIR / "spatial_observations.csv")
class_legend = pd.read_csv(DATA_DIR / "class_legend.csv")
config = json.loads((DATA_DIR / "dashboard_config.json").read_text(encoding="utf-8"))

noaa_timeseries = pd.read_csv(DATA_DIR / "noaa_thermal_timeseries.csv", parse_dates=["date"])
noaa_latest_map = pd.read_csv(DATA_DIR / "noaa_latest_map.csv")
noaa_alert_summary = pd.read_csv(DATA_DIR / "noaa_alert_summary.csv")
noaa_config = json.loads((DATA_DIR / "noaa_config.json").read_text(encoding="utf-8"))
```

## Campos NOAA principais

| Campo | Significado | Gráfico |
|---|---|---|
| `dhw_celsius_weeks_mean` / `dhw_celsius_weeks_max` | Estresse térmico acumulado | Série temporal e KPI |
| `hotspot_c_mean` / `hotspot_c_max` | HotSpot | Série temporal e mapa |
| `sst_c_mean` | Temperatura da superfície do mar | Série temporal |
| `sst_anomaly_c_mean` | Anomalia da SST | Série temporal |
| `baa_7d_max` | Alerta máximo NOAA em 7 dias, classes 0–4 | Mapa categórico |
| `alert_label` / `pixel_percent` | Rótulo e percentual de pixels por nível | Cards/barra empilhada |

Níveis BAA: 0 No Stress; 1 Bleaching Watch; 2 Bleaching Warning; 3 Alert Level 1; 4 Alert Level 2.

## Páginas sugeridas

1. **Overview:** quantidade de voos, período histórico NASA, data mais recente NOAA e mapa geral.
2. **NASA CORAL — Reef Composition:** filtros por voo/variável, estatísticas com unidade, distribuição/boxplot, mapas quando houver coordenadas.
3. **NOAA — Environmental Monitoring:** linhas temporais DHW/HotSpot/SST/anomalia e mapa térmico.
4. **NOAA — Early Warning:** cards BAA, mapa categórico, distribuição por nível e data de observação.
5. **Methodology & Sources:** explicar fontes, períodos, resolução, DOI, ERDDAP e limitações.

## Regras de interpretação

1. Não afirmar que NASA CORAL mede a saúde atual do recife.
2. Não interpretar BAA como diagnóstico de mortalidade individual.
3. `pixel_percent` é percentual dos pixels oceânicos válidos na caixa consultada — não percentual de colônias nem de área recifal.
4. Sem máscara de recife, estatísticas NOAA descrevem o recorte geográfico, não exclusivamente os recifes.
5. Não comparar cobertura bentônica entre voos como tendência temporal sem validar comparabilidade de variáveis, processamento, área e aquisição.
6. Sempre exibir data, fonte e unidade.
7. Se um CSV vier vazio ou não tiver coordenadas, mostrar aviso explicativo em vez de inventar resultados.
8. `benthic_variable_summary.csv` usa amostragem regular quando necessário; seus campos terminam em `_sampled` para deixar isso explícito.
