"""Validate masks and probability consistency in NASA CORAL PRISM NetCDF files.

Run from the project root with:
    python -m coralwatch.validate_masks

The script reads the NetCDF files in blocks and does not load the full files
into memory.
"""

from pathlib import Path

import numpy as np
from netCDF4 import Dataset


DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "nasa"
VARIABLES = ("coral", "algae", "sand")
BLOCK_SIZE = 256
PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
SUM_TOLERANCE = 0.05


def inspect_file(file_path: Path) -> None:
    """Inspect valid/masked pixels and class-probability sums for one file."""
    print("\n" + "=" * 68)
    print(f"ARQUIVO: {file_path.name}")
    print("=" * 68)

    with Dataset(file_path, mode="r") as nc:
        if "derived_data" not in nc.groups:
            raise KeyError("Grupo 'derived_data' não encontrado no arquivo.")
        if "navigation_data" not in nc.groups:
            raise KeyError("Grupo 'navigation_data' não encontrado no arquivo.")

        derived = nc.groups["derived_data"]

        missing_variables = [name for name in VARIABLES if name not in derived.variables]
        if missing_variables:
            raise KeyError(
                "Variáveis bentônicas ausentes em /derived_data/: "
                + ", ".join(missing_variables)
            )

        # As dimensões são declaradas na raiz do NetCDF, e não no grupo
        # derived_data. Obtemos o formato diretamente da variável coral.
        coral_shape = derived.variables["coral"].shape
        if len(coral_shape) != 2:
            raise ValueError(
                f"Esperada variável coral 2D (scans, pixels), recebido: {coral_shape}"
            )

        scans, pixels = coral_shape
        total_pixels = scans * pixels
        print(f"Dimensão espacial: {scans:,} scans x {pixels:,} pixels")
        print(f"Total de pixels: {total_pixels:,}")

        # Confirmar que as três classes usam a mesma grade espacial.
        for name in VARIABLES:
            if derived.variables[name].shape != coral_shape:
                raise ValueError(
                    f"A variável '{name}' tem formato {derived.variables[name].shape}; "
                    f"era esperado {coral_shape}."
                )

        stats = {
            name: {
                "valid": 0,
                "masked": 0,
                "non_finite": 0,
                "out_of_range": 0,
                "sum": 0.0,
                "minimum": np.inf,
                "maximum": -np.inf,
            }
            for name in VARIABLES
        }

        # Acumuladores da soma coral + algae + sand, sem guardar todos os
        # pixels em memória.
        common_valid_count = 0
        probability_sum_count = 0
        probability_sum_total = 0.0
        probability_sum_min = np.inf
        probability_sum_max = -np.inf
        probability_sum_within_tolerance = 0

        for start in range(0, scans, BLOCK_SIZE):
            end = min(start + BLOCK_SIZE, scans)
            arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}

            for name in VARIABLES:
                variable = derived.variables[name]
                block = np.ma.asarray(variable[start:end, :])

                mask = np.ma.getmaskarray(block)
                raw = np.asarray(block.data, dtype=np.float64)

                finite = np.isfinite(raw)
                in_range = (
                    (raw >= PROBABILITY_MIN)
                    & (raw <= PROBABILITY_MAX)
                )
                valid = (~mask) & finite & in_range

                values = raw[valid]
                result = stats[name]
                result["valid"] += int(values.size)
                result["masked"] += int(mask.sum())
                result["non_finite"] += int(((~finite) & (~mask)).sum())
                result["out_of_range"] += int(
                    ((~in_range) & finite & (~mask)).sum()
                )

                if values.size:
                    result["sum"] += float(values.sum(dtype=np.float64))
                    result["minimum"] = min(result["minimum"], float(values.min()))
                    result["maximum"] = max(result["maximum"], float(values.max()))

                arrays[name] = (raw, valid)

            # Avaliar a consistência apenas nos pixels válidos nas três classes.
            common = (
                arrays["coral"][1]
                & arrays["algae"][1]
                & arrays["sand"][1]
            )
            common_count = int(common.sum())
            common_valid_count += common_count

            if common_count:
                probability_sum = (
                    arrays["coral"][0][common]
                    + arrays["algae"][0][common]
                    + arrays["sand"][0][common]
                )

                probability_sum_count += int(probability_sum.size)
                probability_sum_total += float(
                    probability_sum.sum(dtype=np.float64)
                )
                probability_sum_min = min(
                    probability_sum_min, float(probability_sum.min())
                )
                probability_sum_max = max(
                    probability_sum_max, float(probability_sum.max())
                )
                probability_sum_within_tolerance += int(
                    (np.abs(probability_sum - 1.0) <= SUM_TOLERANCE).sum()
                )

        print("\n===== MÁSCARAS E VALORES =====")
        for name, result in stats.items():
            count = result["valid"]
            mean = result["sum"] / count if count else np.nan
            minimum = result["minimum"] if count else np.nan
            maximum = result["maximum"] if count else np.nan
            fill_value = getattr(derived.variables[name], "_FillValue", "Não informado")

            print(f"\n{name.upper()}")
            print(f"Fill value: {fill_value}")
            print(f"Pixels válidos: {count:,}")
            print(f"Pixels mascarados: {result['masked']:,}")
            print(f"Valores não finitos não mascarados: {result['non_finite']:,}")
            print(f"Valores fora de [0, 1] não mascarados: {result['out_of_range']:,}")
            print(f"Percentual válido sobre o total: {count / total_pixels * 100:.3f}%")
            print(f"Média: {mean:.6f}")
            print(f"Mínimo: {minimum:.6f}" if count else "Mínimo: sem valores válidos")
            print(f"Máximo: {maximum:.6f}" if count else "Máximo: sem valores válidos")

        print("\n===== INTERSEÇÃO DAS CLASSES =====")
        print(f"Pixels válidos nas três classes: {common_valid_count:,}")

        if probability_sum_count:
            mean_sum = probability_sum_total / probability_sum_count
            within_pct = (
                probability_sum_within_tolerance / probability_sum_count * 100
            )
            print(f"Média da soma das probabilidades: {mean_sum:.6f}")
            print(f"Mínimo da soma: {probability_sum_min:.6f}")
            print(f"Máximo da soma: {probability_sum_max:.6f}")
            print(
                f"Pixels com soma entre 0.95 e 1.05: {within_pct:.2f}%"
            )
        else:
            print("Não há pixels válidos simultaneamente nas três classes.")


def main() -> None:
    files = sorted(DATA_DIR.glob("*.nc"))

    if not files:
        print(f"Nenhum arquivo NetCDF encontrado em: {DATA_DIR}")
        return

    print(f"Total de arquivos encontrados: {len(files)}")

    for file_path in files:
        try:
            inspect_file(file_path)
        except Exception as exc:
            print(f"\nERRO ao validar {file_path.name}: {exc}")


if __name__ == "__main__":
    main()
