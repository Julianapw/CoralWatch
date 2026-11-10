"""
CoralWatch - NOAA Coral Reef Watch v3.1 downloader.

Downloads recent daily CRW data for the geographic footprints of the three
NASA sample flights used in this project. Public data; no login required.

Run from the project root:
    python -m coralwatch.noaa
    python -m coralwatch.noaa --days 30 --refresh

The NASA flights are historical (2016). NOAA values downloaded here are the
latest available values for the same locations and must be displayed separately,
not interpreted as the heat stress that caused the 2016 benthic observations.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "noaa"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Sample NASA L2 footprints, expanded slightly to cover the surrounding reef.
# Format: (south, north, west, east)
FLIGHT_BOUNDS = {
    "PRM2016252225710": (-14.957248, -14.537131, 145.326800, 145.782803),
    "PRM2016266222857": (-19.261510, -18.874604, 152.267841, 152.496945),
    "PRM2016287001832": (-11.460237, -10.737195, 142.756396, 143.959164),
}

VARIABLES = [
    "CRW_SST",
    "CRW_SSTANOMALY",
    "CRW_HOTSPOT",
    "CRW_DHW",
    "CRW_BAA_7D_MAX",
]

# NOAA lists these public ERDDAP mirrors for its daily global 5-km product.
ERDDAP_ENDPOINTS = [
    (
        "PacIOOS",
        "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/dhw_5km",
        "dhw_5km",
    ),
    (
        "NOAA CoastWatch West Coast",
        "https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW",
        "NOAA_DHW",
    ),
    (
        "NOAA Upwell",
        "https://upwell.pfeg.noaa.gov/erddap/griddap/dhw_5km",
        "dhw_5km",
    ),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("coralwatch.noaa")


def build_erddap_url(bounds, days, dataset_url):
    """Build a valid ERDDAP griddap NetCDF subset request.

    ERDDAP expects coordinate constraints directly after each variable:
    variable[time-start:stride:time-end][lat-start:stride:lat-end][lon-start:stride:lon-end]
    It does not expect dimension names inside the brackets.
    """
    south, north, west, east = bounds

    # ERDDAP griddap uses array-index stride values (integers), not degrees.
    # Parentheses mark coordinate values; last-N is an index expression and
    # therefore must NOT be wrapped in parentheses.
    # CRW latitude is descending, and ERDDAP handles high-to-low bounds.
    time_constraint = f"[last-{days - 1}:1:last]"
    latitude_constraint = f"[({north}):1:({south})]"
    longitude_constraint = f"[({west}):1:({east})]"

    selections = ",".join(
        f"{name}{time_constraint}{latitude_constraint}{longitude_constraint}"
        for name in VARIABLES
    )
    return f"{dataset_url}.nc?{quote(selections, safe='[]():,.*-')}"


def is_netcdf(path):
    """Check classic NetCDF or HDF5/NetCDF4 file signatures."""
    with path.open("rb") as file:
        signature = file.read(8)
    return signature.startswith(b"CDF") or signature == b"\x89HDF\r\n\x1a\n"


def download_subset(flight_id, bounds, days, refresh=False):
    output_path = RAW_DIR / f"{flight_id}_NOAA_last_{days}_days.nc"

    if output_path.exists() and output_path.stat().st_size > 0 and not refresh:
        logger.info("Usando cache existente: %s", output_path.name)
        return output_path

    errors = []
    for server_name, base_url, _dataset_id in ERDDAP_ENDPOINTS:
        url = build_erddap_url(bounds, days, base_url)
        partial_path = output_path.with_suffix(".nc.part")
        logger.info("Consultando %s para %s...", server_name, flight_id)

        try:
            with requests.get(
                url,
                stream=True,
                timeout=(20, 240),
                headers={"User-Agent": "CoralWatch/1.0 (educational research project)"},
            ) as response:
                if response.status_code >= 400:
                    # ERDDAP usually returns the exact reason for HTTP 400 in
                    # its response body; preserve it instead of hiding it.
                    detail = response.text[:2000]
                    raise RuntimeError(
                        f"HTTP {response.status_code} em {server_name}. "
                        f"Resposta ERDDAP: {detail}"
                    )
                with partial_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file.write(chunk)

            if not partial_path.exists() or partial_path.stat().st_size < 100:
                raise RuntimeError("A resposta do servidor veio vazia ou muito pequena.")
            if not is_netcdf(partial_path):
                preview = partial_path.read_bytes()[:300].decode("utf-8", errors="replace")
                raise RuntimeError(f"O servidor não retornou um NetCDF válido: {preview}")

            partial_path.replace(output_path)
            logger.info(
                "Download concluído (%s): %.2f MB",
                server_name,
                output_path.stat().st_size / (1024 * 1024),
            )
            return output_path

        except Exception as exc:
            errors.append(f"{server_name}: {exc}")
            logger.warning("%s falhou: %s", server_name, exc)
            try:
                partial_path.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(1)

    raise RuntimeError(
        f"Não foi possível baixar os dados NOAA para {flight_id}.\n"
        + "\n".join(errors)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Baixa dados recentes do NOAA Coral Reef Watch para as áreas dos voos NASA."
    )
    parser.add_argument("--days", type=int, default=30, help="Número de dias (padrão: 30).")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Baixa novamente mesmo que já exista um arquivo em cache.",
    )
    args = parser.parse_args()

    if args.days < 1 or args.days > 365:
        parser.error("--days deve estar entre 1 e 365.")

    results = []
    for flight_id, bounds in FLIGHT_BOUNDS.items():
        try:
            path = download_subset(flight_id, bounds, args.days, args.refresh)
            results.append(
                {
                    "flight_id": flight_id,
                    "file": str(path.relative_to(PROJECT_ROOT)),
                    "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                    "status": "downloaded_or_cached",
                }
            )
        except Exception as exc:
            logger.error("%s", exc)
            results.append(
                {"flight_id": flight_id, "status": "failed", "error": str(exc)}
            )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "product": "NOAA Coral Reef Watch v3.1 daily global 5km",
        "days_requested": args.days,
        "variables": VARIABLES,
        "note": (
            "NOAA recent conditions are separate from the historical 2016 NASA "
            "benthic observations; they do not explain or establish the cause "
            "of those observations."
        ),
        "results": results,
    }
    report_path = OUTPUT_DIR / "noaa_download_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    successful = sum(item["status"] != "failed" for item in results)
    logger.info("Finalizado: %s/%s áreas baixadas ou em cache.", successful, len(results))
    logger.info("Relatório: %s", report_path)


if __name__ == "__main__":
    main()
