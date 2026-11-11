
"""Historical NOAA SST visualization for CoralWatch."""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.charts import plot
from core.components import section_header


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_FILE = PROJECT_ROOT / "data" / "processed" / "noaa_sst_history_daily.csv"


@st.cache_data(show_spinner=False)
def load_history(file_path, modified_time, file_size):
    """Load and validate the historical NOAA SST CSV."""

    path = Path(file_path)

    if not path.exists():
        return pd.DataFrame(), "Arquivo histórico não encontrado."

    try:
        data = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        return pd.DataFrame(), f"Não foi possível ler o arquivo: {exc}"

    required = {"region", "date", "SST_mean"}

    missing = required - set(data.columns)

    if missing:
        return (
            pd.DataFrame(),
            "Colunas obrigatórias ausentes: " + ", ".join(sorted(missing)),
        )

    data = data.copy()

    data["region"] = data["region"].astype(str).str.strip()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["sst_mean"] = pd.to_numeric(data["SST_mean"], errors="coerce")

    if "SST_min" in data.columns:
        data["sst_min"] = pd.to_numeric(data["SST_min"], errors="coerce")

    if "SST_max" in data.columns:
        data["sst_max"] = pd.to_numeric(data["SST_max"], errors="coerce")

    if "SST_valid_count" in data.columns:
        data["valid_count"] = pd.to_numeric(
            data["SST_valid_count"],
            errors="coerce",
        )

    data = data.dropna(subset=["date", "sst_mean"])
    data = data[data["region"].ne("")]

    # One observation per region and date.
    data = data.drop_duplicates(
        subset=["region", "date"],
        keep="last",
    )

    data = data.sort_values(["region", "date"]).reset_index(drop=True)

    if data.empty:
        return pd.DataFrame(), "O arquivo não contém observações válidas."

    return data, None


def coverage_table(data):
    """Summarize the actual date coverage of each region."""

    coverage = (
        data.groupby("region")
        .agg(
            registros=("date", "count"),
            primeira_data=("date", "min"),
            ultima_data=("date", "max"),
        )
        .reset_index()
    )

    coverage["primeira_data"] = coverage["primeira_data"].dt.strftime(
        "%d/%m/%Y"
    )
    coverage["ultima_data"] = coverage["ultima_data"].dt.strftime(
        "%d/%m/%Y"
    )

    return coverage.rename(
        columns={
            "region": "Região",
            "registros": "Registros",
            "primeira_data": "Primeira data",
            "ultima_data": "Última data",
        }
    )


def add_missing_dates(data):
    """
    Insert NaN rows for missing calendar days.

    This makes gaps visible in the chart instead of connecting
    observations across dates that have no data.
    """

    parts = []

    for region, group in data.groupby("region"):
        group = group.sort_values("date").copy()

        calendar = pd.date_range(
            start=group["date"].min(),
            end=group["date"].max(),
            freq="D",
        )

        group = (
            group.set_index("date")
            .reindex(calendar)
            .rename_axis("date")
            .reset_index()
        )

        group["region"] = region
        parts.append(group)

    return pd.concat(parts, ignore_index=True)


def render_history():
    """Render the historical SST section in the environmental page."""

    st.divider()

    section_header(
        "Histórico de temperatura da superfície do mar",
        "NOAA Coral Reef Watch · série histórica diária de SST (°C)",
        "NOAA",
    )

    if not HISTORY_FILE.exists():
        st.warning(
            "O arquivo noaa_sst_history_daily.csv não foi encontrado "
            "em data/processed/."
        )
        return

    stat = HISTORY_FILE.stat()

    data, error = load_history(
        str(HISTORY_FILE),
        stat.st_mtime_ns,
        stat.st_size,
    )

    if error:
        st.warning(error)
        return

    st.caption(
        "Esta série apresenta a média diária de SST dos pixels válidos "
        "em cada recorte geográfico. Ela é independente dos indicadores "
        "recentes de DHW, HotSpot e BAA."
    )

    regions = sorted(data["region"].unique().tolist())

    selected_region = st.selectbox(
        "Região da série histórica",
        ["Todas as regiões"] + regions,
        key="history_region",
    )

    if selected_region != "Todas as regiões":
        filtered = data[data["region"] == selected_region].copy()
    else:
        filtered = data.copy()

    min_date = filtered["date"].min().date()
    max_date = filtered["date"].max().date()

    selected_dates = st.date_input(
        "Período da série histórica",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="history_dates",
    )

    if len(selected_dates) != 2:
        st.info("Selecione uma data inicial e uma data final.")
        return

    start_date, end_date = selected_dates

    filtered = filtered[
        filtered["date"].dt.date.between(start_date, end_date)
    ].copy()

    if filtered.empty:
        st.info("Não existem observações para o período selecionado.")
        return

    columns = st.columns(3)

    with columns[0]:
        st.metric("Observações", f"{len(filtered):,}")

    with columns[1]:
        st.metric("Regiões", filtered["region"].nunique())

    with columns[2]:
        days = (end_date - start_date).days + 1
        st.metric("Dias no intervalo", f"{days:,}")

    st.caption(
        f"Período observado: {filtered.date.min():%d/%m/%Y} "
        f"a {filtered.date.max():%d/%m/%Y}"
    )

    # Preserve missing dates as gaps in the line chart.
    chart_data = add_missing_dates(filtered)

    fig = px.line(
        chart_data,
        x="date",
        y="sst_mean",
        color="region",
        labels={
            "date": "Data",
            "sst_mean": "SST média (°C)",
            "region": "Região",
        },
        hover_data={
            "date": "|%d/%m/%Y",
            "sst_mean": ":.2f",
            "region": True,
        },
    )

    fig.update_traces(connectgaps=False)
    fig.update_xaxes(tickformat="%Y")
    fig.update_yaxes(title="Temperatura (°C)")

    plot(fig)

    st.caption(
        "Os espaços sem linha representam dias sem observações no arquivo. "
        "Não foi realizada interpolação ou preenchimento de dados ausentes."
    )

    section_header(
        "Cobertura dos dados",
        "Quantidade de observações e intervalo disponível por região",
    )

    st.dataframe(
        coverage_table(filtered),
        hide_index=True,
        width="stretch",
    )

    st.download_button(
        "Baixar histórico filtrado (CSV)",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        "coralwatch_noaa_sst_history.csv",
        "text/csv",
        key="download_sst_history",
    )
