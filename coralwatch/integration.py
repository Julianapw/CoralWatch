
from pathlib import Path

import pandas as pd


# ============================================================
# 1. CAMINHOS
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]

PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

NASA_CATALOG = PROCESSED_DIR / "flight_catalog.csv"
NASA_BENTHIC = PROCESSED_DIR / "benthic_variable_summary.csv"
NASA_QUALITY = PROCESSED_DIR / "nasa_pixel_quality.csv"

NOAA_SPATIAL = PROCESSED_DIR / "noaa_spatial_summary.csv"
NOAA_DAILY = PROCESSED_DIR / "noaa_daily_summary.csv"

OUTPUT_FILE = PROCESSED_DIR / "integrated_regional_summary.csv"


# ============================================================
# 2. FUNÇÃO PARA PADRONIZAR A IDENTIFICAÇÃO DAS REGIÕES
# ============================================================

def normalize_region(value):
    """
    Padroniza o identificador da região para permitir
    a correspondência entre NASA e NOAA.
    """

    return str(value).strip().lower()


# ============================================================
# 3. CARREGAMENTO DOS ARQUIVOS
# ============================================================

def load_data():

    required_files = [
        NASA_CATALOG,
        NASA_BENTHIC,
        NASA_QUALITY,
        NOAA_SPATIAL,
        NOAA_DAILY,
    ]

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(
                f"Arquivo não encontrado: {path}"
            )

    catalog = pd.read_csv(NASA_CATALOG)
    benthic = pd.read_csv(NASA_BENTHIC)
    quality = pd.read_csv(NASA_QUALITY)
    noaa_spatial = pd.read_csv(NOAA_SPATIAL)
    noaa_daily = pd.read_csv(NOAA_DAILY)

    return catalog, benthic, quality, noaa_spatial, noaa_daily


# ============================================================
# 4. ORGANIZAÇÃO DOS DADOS BENTÔNICOS DA NASA
# ============================================================

def prepare_nasa_benthic(benthic):

    variables = ["coral", "algae", "sand"]

    statistics = [
        "mean",
        "minimum",
        "median_sampled",
        "maximum",
        "valid_count",
    ]

    # Mantém apenas as variáveis e estatísticas desejadas
    benthic = benthic[
        benthic["variable"].isin(variables)
    ].copy()

    # Cada região deve possuir uma observação por variável
    if benthic.duplicated(
        subset=["flight_line", "variable"]
    ).any():
        raise ValueError(
            "Existem variáveis bentônicas duplicadas "
            "para uma mesma região."
        )

    # Transforma coral, algae e sand em colunas
    pivot = benthic.pivot(
        index="flight_line",
        columns="variable",
        values=statistics,
    )

    # Achata os nomes das colunas
    pivot.columns = [
        f"{variable}_{statistic}"
        for statistic, variable in pivot.columns
    ]

    pivot = pivot.reset_index()

    return pivot


# ============================================================
# 5. ORGANIZAÇÃO DA QUALIDADE DOS DADOS NASA
# ============================================================

def prepare_nasa_quality(quality):

    columns = [
        "flight_line",
        "spatial_sample_points",
        "spatial_sample_valid_points",
        "spatial_sample_masked_points",
        "spatial_sample_valid_pct",
    ]

    quality = quality[columns].copy()

    return quality


# ============================================================
# 6. ORGANIZAÇÃO DO PERÍODO NOAA
# ============================================================

def prepare_noaa_period(noaa_daily):

    noaa_daily["date"] = pd.to_datetime(
        noaa_daily["date"]
    )

    period = (
        noaa_daily
        .groupby("region")
        .agg(
            noaa_period_start=("date", "min"),
            noaa_period_end=("date", "max"),
            noaa_days_observed=("date", "nunique"),
        )
        .reset_index()
    )

    period["noaa_period_start"] = (
        period["noaa_period_start"].dt.strftime("%Y-%m-%d")
    )

    period["noaa_period_end"] = (
        period["noaa_period_end"].dt.strftime("%Y-%m-%d")
    )

    return period


# ============================================================
# 7. INTEGRAÇÃO NASA + NOAA
# ============================================================

def integrate_data():

    print("Carregando arquivos...")

    (
        catalog,
        benthic,
        quality,
        noaa_spatial,
        noaa_daily,
    ) = load_data()

    # --------------------------------------------------------
    # 7.1 PADRONIZA AS CHAVES
    # --------------------------------------------------------

    catalog["region_id"] = catalog["flight_line"].apply(
        normalize_region
    )

    benthic["flight_line"] = benthic["flight_line"].apply(
        normalize_region
    )

    quality["flight_line"] = quality["flight_line"].apply(
        normalize_region
    )

    noaa_spatial["region_id"] = noaa_spatial["region"].apply(
        normalize_region
    )

    noaa_daily["region"] = noaa_daily["region"].apply(
        normalize_region
    )

    # --------------------------------------------------------
    # 7.2 PREPARA AS TABELAS
    # --------------------------------------------------------

    print("Organizando variáveis bentônicas...")

    benthic_pivot = prepare_nasa_benthic(benthic)

    quality_prepared = prepare_nasa_quality(quality)

    noaa_period = prepare_noaa_period(noaa_daily)

    # --------------------------------------------------------
    # 7.3 SELECIONA OS METADADOS NASA
    # --------------------------------------------------------

    nasa_columns = [
        "flight_line",
        "region",
        "observation_date",
        "latitude_min",
        "latitude_max",
        "longitude_min",
        "longitude_max",
        "spatial_resolution",
        "processing_level",
        "total_pixels",
        "valid_benthic_pixels",
        "masked_or_invalid_benthic_pixels",
        "valid_benthic_pixel_pct",
        "masked_or_invalid_benthic_pixel_pct",
    ]

    nasa = catalog[nasa_columns + ["region_id"]].copy()

    nasa = nasa.rename(
        columns={
            "region": "nasa_region",
            "observation_date": "nasa_observation_date",
        }
    )

    # --------------------------------------------------------
    # 7.4 CONFERE AS REGIÕES
    # --------------------------------------------------------

    nasa_regions = set(nasa["region_id"])
    noaa_regions = set(noaa_spatial["region_id"])

    if nasa_regions != noaa_regions:

        missing_noaa = nasa_regions - noaa_regions
        missing_nasa = noaa_regions - nasa_regions

        raise ValueError(
            "As regiões NASA e NOAA não correspondem.\n"
            f"Ausentes na NOAA: {missing_noaa}\n"
            f"Ausentes na NASA: {missing_nasa}"
        )

    # --------------------------------------------------------
    # 7.5 REALIZA OS MERGES
    # --------------------------------------------------------

    print("Integrando dados NASA e NOAA...")

    integrated = nasa.merge(
        benthic_pivot,
        on="flight_line",
        how="left",
        validate="one_to_one",
    )

    integrated = integrated.merge(
        quality_prepared,
        on="flight_line",
        how="left",
        validate="one_to_one",
    )

    integrated = integrated.merge(
        noaa_spatial.drop(columns=["region"]),
        on="region_id",
        how="left",
        validate="one_to_one",
    )

    integrated = integrated.merge(
        noaa_period,
        left_on="region_id",
        right_on="region",
        how="left",
        validate="one_to_one",
    )

    integrated = integrated.drop(columns=["region"])

    # --------------------------------------------------------
    # 7.6 ADICIONA METADADOS DA INTEGRAÇÃO
    # --------------------------------------------------------

    integrated["nasa_source"] = "NASA CORAL PRISM L2"
    integrated["noaa_source"] = "NOAA Coral Reef Watch v3.1"

    integrated["nasa_spatial_resolution"] = (
        "Approximately 7.9 meters"
    )

    integrated["noaa_spatial_resolution"] = (
        "Approximately 5 kilometers"
    )

    integrated["temporal_comparability"] = (
        "Different observation periods; "
        "not a direct temporal comparison"
    )

    integrated["spatial_comparability"] = (
        "Regional summary only; "
        "different spatial resolutions"
    )

    # --------------------------------------------------------
    # 7.7 VERIFICA RESULTADOS
    # --------------------------------------------------------

    if integrated["coral_mean"].isna().any():
        raise ValueError(
            "Existem regiões sem dados de coral."
        )

    if integrated["SST_mean"].isna().any():
        raise ValueError(
            "Existem regiões sem dados de temperatura NOAA."
        )

    if len(integrated) != len(nasa):
        raise ValueError(
            "A quantidade de regiões mudou durante a integração."
        )

    # Organiza as linhas
    integrated = integrated.sort_values(
        "flight_line"
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # 7.8 SALVA O RESULTADO
    # --------------------------------------------------------

    integrated.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    print("\nIntegração concluída!")
    print(f"Arquivo gerado: {OUTPUT_FILE}")
    print(f"Regiões integradas: {len(integrated)}")
    print(f"Total de colunas: {len(integrated.columns)}")

    print("\nResumo integrado:")

    summary_columns = [
        "flight_line",
        "nasa_observation_date",
        "coral_mean",
        "algae_mean",
        "sand_mean",
        "SST_mean",
        "HOTSPOT_mean",
        "DHW_max",
        "BAA_max",
    ]

    print(
        integrated[summary_columns].to_string(
            index=False
        )
    )


# ============================================================
# 8. EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    integrate_data()
