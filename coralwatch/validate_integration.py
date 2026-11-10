
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]

FILE = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "integrated_regional_summary.csv"
)


def main():

    print("Validando integração NASA + NOAA...\n")

    if not FILE.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {FILE}"
        )

    df = pd.read_csv(FILE)

    # 1. Quantidade de regiões
    print("1. Quantidade de regiões:")
    print(len(df))

    assert len(df) == 3, (
        "Esperávamos exatamente 3 regiões."
    )

    # 2. Verifica duplicações
    print("\n2. Verificando regiões duplicadas:")

    duplicates = df["flight_line"].duplicated().sum()

    print(f"Duplicações: {duplicates}")

    assert duplicates == 0

    # 3. Verifica valores ausentes
    print("\n3. Valores ausentes:")

    important_columns = [
        "coral_mean",
        "algae_mean",
        "sand_mean",
        "SST_mean",
        "HOTSPOT_mean",
        "DHW_max",
        "BAA_max",
    ]

    missing = df[important_columns].isna().sum()

    print(missing.to_string())

    assert missing.sum() == 0, (
        "Existem valores ausentes nos indicadores principais."
    )

    # 4. Verifica soma das probabilidades bentônicas
    print("\n4. Soma das probabilidades bentônicas:")

    probability_sum = (
        df["coral_mean"]
        + df["algae_mean"]
        + df["sand_mean"]
    )

    for region, total in zip(
        df["flight_line"],
        probability_sum
    ):
        print(f"{region}: {total:.6f}")

    assert np.allclose(
        probability_sum,
        1.0,
        atol=0.0001
    ), "As probabilidades não somam aproximadamente 1."

    # 5. Verifica os indicadores NOAA
    print("\n5. Indicadores térmicos NOAA:")

    print(
        df[
            [
                "flight_line",
                "SST_mean",
                "HOTSPOT_mean",
                "DHW_max",
                "BAA_max",
            ]
        ].to_string(index=False)
    )

    assert (df["BAA_max"] >= 0).all()
    assert (df["BAA_max"] <= 4).all()
    assert (df["DHW_max"] >= 0).all()

    # 6. Verifica períodos separados
    print("\n6. Períodos de observação:")

    print(
        df[
            [
                "flight_line",
                "nasa_observation_date",
                "noaa_period_start",
                "noaa_period_end",
            ]
        ].to_string(index=False)
    )

    assert df["noaa_period_start"].notna().all()
    assert df["noaa_period_end"].notna().all()

    # 7. Resultado final
    print("\n" + "=" * 55)
    print("VALIDAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 55)


if __name__ == "__main__":
    main()
