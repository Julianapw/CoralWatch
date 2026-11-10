from pathlib import Path
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
FILE = PROJECT_DIR / "data" / "processed" / "noaa_daily_summary.csv"


def main():
    df = pd.read_csv(FILE)

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()

    print("VALIDAÇÃO DAS DATAS NOAA\n")

    for region, group in df.groupby("region"):
        dates = sorted(group["date"].dropna().unique())

        expected_dates = pd.date_range(
            start=dates[0],
            end=dates[-1],
            freq="D"
        )

        missing_dates = expected_dates.difference(dates)

        print(f"Região: {region}")
        print(f"Quantidade de registros: {len(dates)}")
        print(f"Primeira data: {dates[0].date()}")
        print(f"Última data: {dates[-1].date()}")
        print(f"Dias corridos no intervalo: {len(expected_dates)}")
        print(f"Dias sem registros: {len(missing_dates)}")

        if len(missing_dates) > 0:
            print("Datas ausentes:")
            for date in missing_dates:
                print(f"  - {date.date()}")

        print("-" * 50)


if __name__ == "__main__":
    main()