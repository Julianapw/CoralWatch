"""Command-line entry point for the CoralWatch data pipeline."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import pandas as pd

from . import settings
from .nasa import ensure_directories, process_nasa_files
from .noaa import process_noaa_data


def create_dashboard_package() -> Path:
    """Zip all processed outputs that currently exist for the Streamlit teammate."""
    settings.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    output_files = settings.NASA_OUTPUTS + settings.NOAA_OUTPUTS
    existing = [
        filename for filename in output_files
        if (settings.PROCESSED_DIR / filename).exists()
    ]
    if not existing:
        raise RuntimeError("Nenhum arquivo processado foi encontrado para empacotar.")

    package_path = settings.DOWNLOADS_DIR / "coralwatch_dashboard_data.zip"
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in existing:
            archive.write(
                settings.PROCESSED_DIR / filename,
                arcname=f"processed/{filename}",
            )
    print(f"[EXPORT] Pacote do dashboard criado: {package_path}")
    print(f"[EXPORT] {len(existing)} arquivo(s) incluído(s).")
    return package_path


def load_flight_catalog() -> pd.DataFrame | None:
    catalog_path = settings.PROCESSED_DIR / "flight_catalog.csv"
    if catalog_path.exists():
        return pd.read_csv(catalog_path)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepara dados NASA CORAL e NOAA Coral Reef Watch para o CoralWatch."
    )
    parser.add_argument(
        "--source",
        choices=("all", "nasa", "noaa"),
        default="all",
        help="Fonte a processar (padrão: all).",
    )
    parser.add_argument(
        "--noaa-file",
        type=Path,
        default=None,
        help="Opcional: usar um NetCDF NOAA já baixado em vez de consultar o ERDDAP.",
    )
    args = parser.parse_args()

    ensure_directories()
    flight_catalog = load_flight_catalog()

    if args.source in ("all", "nasa"):
        flight_catalog = process_nasa_files()

    if args.source in ("all", "noaa"):
        if args.source == "noaa" and flight_catalog is None:
            print(
                "[AVISO] flight_catalog.csv não encontrado. "
                "Será usada a bounding box de fallback configurada em coralwatch/settings.py."
            )
        process_noaa_data(
            flight_catalog=flight_catalog,
            use_existing_file=args.noaa_file,
        )

    create_dashboard_package()
    print("\nCoralWatch: pipeline finalizado.")


if __name__ == "__main__":
    main()
