
from pathlib import Path
import pandas as pd

DATA_DIR = Path("data/processed")

catalog = pd.read_csv(DATA_DIR / "flight_catalog.csv")
summary = pd.read_csv(DATA_DIR / "benthic_variable_summary.csv")

# Calcular o total de pixels por voo
catalog["total_pixels"] = (
    catalog["number_of_scans"] *
    catalog["pixels_per_scan"]
)

# Selecionar apenas as estatísticas da variável coral
valid_pixels = summary[
    summary["variable"] == "coral"
][["source_file", "valid_count"]]

# Combinar informações
report = catalog.merge(
    valid_pixels,
    on="source_file",
    how="left"
)

# Calcular percentual de pixels válidos
report["valid_pixel_pct"] = (
    report["valid_count"] /
    report["total_pixels"] * 100
)

print("\n===== RELATÓRIO DE QUALIDADE NASA =====")

print(
    report[[
        "flight_line",
        "total_pixels",
        "valid_count",
        "valid_pixel_pct"
    ]].to_string(index=False)
)

print("\n===== COMPOSIÇÃO BENTÔNICA =====")

for variable in ["coral", "algae", "sand"]:

    result = summary[
        summary["variable"] == variable
    ]

    print(f"\n{variable.upper()}")

    print(
        result[[
            "source_file",
            "mean"
        ]].to_string(index=False)
    )
