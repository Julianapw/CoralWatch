
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset, num2date


# ============================================================
# 1. CAMINHOS DO PROJETO
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]

INPUT_DIR = PROJECT_DIR / "data" / "raw" / "noaa"
OUTPUT_DIR = PROJECT_DIR / "data" / "processed"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. VARIÁVEIS QUE SERÃO ANALISADAS
# ============================================================

CONTINUOUS_VARIABLES = [
    "CRW_SST",
    "CRW_SSTANOMALY",
    "CRW_HOTSPOT",
    "CRW_DHW",
]

BAA_VARIABLE = "CRW_BAA_7D_MAX"

BAA_LEVELS = {
    0: "no_stress",
    1: "bleaching_watch",
    2: "bleaching_warning",
    3: "alert_level_1",
    4: "alert_level_2",
}


# ============================================================
# 3. FUNÇÃO PARA LER OS VALORES VÁLIDOS
# ============================================================

def read_valid_values(variable):
    """
    Lê uma variável NetCDF e transforma valores ausentes
    ou fora do intervalo válido em NaN.
    """

    values = np.ma.asarray(variable[:]).astype(float)

    # Converte valores mascarados em NaN
    values = values.filled(np.nan)

    # Aplica os limites válidos definidos nos metadados
    valid_min = getattr(variable, "valid_min", None)
    valid_max = getattr(variable, "valid_max", None)

    if valid_min is not None:
        values[values < float(valid_min)] = np.nan

    if valid_max is not None:
        values[values > float(valid_max)] = np.nan

    return values


# ============================================================
# 4. FUNÇÕES AUXILIARES
# ============================================================

def calculate_statistics(values):
    """
    Calcula estatísticas básicas ignorando NaN.
    """

    valid = values[np.isfinite(values)]

    if valid.size == 0:
        return {
            "mean": np.nan,
            "min": np.nan,
            "max": np.nan,
            "valid_count": 0,
        }

    return {
        "mean": float(np.mean(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "valid_count": int(valid.size),
    }


def add_baa_statistics(row, values):
    """
    Adiciona ao resultado a distribuição dos níveis
    de alerta de branqueamento.
    """

    valid = values[np.isfinite(values)]

    if valid.size == 0:
        row["BAA_max"] = np.nan

        for level, name in BAA_LEVELS.items():
            row[f"BAA_{name}_count"] = 0
            row[f"BAA_{name}_percentage"] = np.nan

        return row

    row["BAA_max"] = int(np.max(valid))

    for level, name in BAA_LEVELS.items():
        count = int(np.sum(valid == level))

        row[f"BAA_{name}_count"] = count
        row[f"BAA_{name}_percentage"] = (
            count / valid.size * 100
        )

    return row


# ============================================================
# 5. ANÁLISE DOS ARQUIVOS NOAA
# ============================================================

def analyze_noaa_file(path):

    print(f"\nAnalisando: {path.name}")

    daily_results = []
    spatial_result = {
        "region": path.name.replace(
            "_NOAA_last_30_days.nc", ""
        )
    }

    with Dataset(path, mode="r") as ds:

        # Identificação das datas
        time_variable = ds.variables["time"]

        dates = num2date(
            time_variable[:],
            units=time_variable.units,
            calendar=getattr(
                time_variable,
                "calendar",
                "standard"
            ),
            only_use_cftime_datetimes=False,
            only_use_python_datetimes=True,
        )

        # Lê todas as variáveis necessárias
        data = {}

        for variable_name in CONTINUOUS_VARIABLES:
            data[variable_name] = read_valid_values(
                ds.variables[variable_name]
            )

        baa_data = read_valid_values(
            ds.variables[BAA_VARIABLE]
        )

        # ----------------------------------------------------
        # 5.1 RESUMO DIÁRIO
        # ----------------------------------------------------

        for time_index, date in enumerate(dates):

            row = {
                "region": spatial_result["region"],
                "date": date.strftime("%Y-%m-%d"),
            }

            for variable_name in CONTINUOUS_VARIABLES:

                daily_values = data[variable_name][time_index]

                stats = calculate_statistics(daily_values)

                prefix = variable_name.replace("CRW_", "")

                row[f"{prefix}_mean"] = stats["mean"]
                row[f"{prefix}_min"] = stats["min"]
                row[f"{prefix}_max"] = stats["max"]
                row[f"{prefix}_valid_count"] = (
                    stats["valid_count"]
                )

            # BAA é uma classificação, não uma temperatura.
            # Por isso, calculamos contagens e porcentagens.
            row = add_baa_statistics(
                row,
                baa_data[time_index]
            )

            daily_results.append(row)

        # ----------------------------------------------------
        # 5.2 RESUMO ESPACIAL DO PERÍODO
        # ----------------------------------------------------

        for variable_name in CONTINUOUS_VARIABLES:

            stats = calculate_statistics(
                data[variable_name].flatten()
            )

            prefix = variable_name.replace("CRW_", "")

            spatial_result[f"{prefix}_mean"] = stats["mean"]
            spatial_result[f"{prefix}_min"] = stats["min"]
            spatial_result[f"{prefix}_max"] = stats["max"]
            spatial_result[f"{prefix}_valid_count"] = (
                stats["valid_count"]
            )

        spatial_result = add_baa_statistics(
            spatial_result,
            baa_data.flatten()
        )

        spatial_result["number_of_days"] = len(dates)

        spatial_result["latitude_min"] = float(
            np.min(ds.variables["latitude"][:])
        )

        spatial_result["latitude_max"] = float(
            np.max(ds.variables["latitude"][:])
        )

        spatial_result["longitude_min"] = float(
            np.min(ds.variables["longitude"][:])
        )

        spatial_result["longitude_max"] = float(
            np.max(ds.variables["longitude"][:])
        )

    return daily_results, spatial_result


# ============================================================
# 6. EXECUÇÃO DA ANÁLISE
# ============================================================

def main():

    files = sorted(
        INPUT_DIR.glob("*_NOAA_last_30_days.nc")
    )

    if not files:
        print("Nenhum arquivo NOAA encontrado.")
        return

    all_daily_results = []
    all_spatial_results = []

    print(f"Arquivos encontrados: {len(files)}")

    for path in files:

        daily_results, spatial_result = analyze_noaa_file(
            path
        )

        all_daily_results.extend(daily_results)
        all_spatial_results.append(spatial_result)

    # Converte os resultados em DataFrames
    daily_df = pd.DataFrame(all_daily_results)
    spatial_df = pd.DataFrame(all_spatial_results)

    # Salva os CSVs
    daily_path = OUTPUT_DIR / "noaa_daily_summary.csv"
    spatial_path = OUTPUT_DIR / "noaa_spatial_summary.csv"

    daily_df.to_csv(
        daily_path,
        index=False,
        encoding="utf-8"
    )

    spatial_df.to_csv(
        spatial_path,
        index=False,
        encoding="utf-8"
    )

    print("\nAnálise concluída!")

    print(f"\nResumo diário: {daily_path}")
    print(f"Registros: {len(daily_df)}")

    print(f"\nResumo espacial: {spatial_path}")
    print(f"Registros: {len(spatial_df)}")

    print("\nResumo das regiões:")
    print(
        spatial_df[
            [
                "region",
                "SST_mean",
                "SSTANOMALY_mean",
                "HOTSPOT_mean",
                "DHW_max",
                "BAA_max",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
