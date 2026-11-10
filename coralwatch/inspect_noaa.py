
from pathlib import Path
from netCDF4 import Dataset
import numpy as np

DATA_DIR = Path("data/raw/noaa")

files = sorted(DATA_DIR.glob("*_NOAA_last_30_days.nc"))

print(f"Arquivos encontrados: {len(files)}")

for file_path in files:
    print("\n" + "=" * 65)
    print(f"ARQUIVO: {file_path.name}")
    print("=" * 65)

    with Dataset(file_path, "r") as ds:

        print("\nDimensões:")
        for name, dimension in ds.dimensions.items():
            print(f"  {name}: {len(dimension)}")

        print("\nVariáveis:")

        for name, variable in ds.variables.items():
            values = variable[:]

            if np.ma.isMaskedArray(values):
                valid = values.compressed()
            else:
                valid = np.asarray(values).flatten()
                valid = valid[np.isfinite(valid)]

            print(f"\n  {name}")
            print(f"    Dimensões: {variable.dimensions}")
            print(f"    Formato: {variable.shape}")
            print(f"    Unidade: {getattr(variable, 'units', 'não informada')}")
            print(f"    Valores válidos: {valid.size}")

            if valid.size > 0:
                print(f"    Mínimo: {valid.min():.4f}")
                print(f"    Máximo: {valid.max():.4f}")
                print(f"    Média: {valid.mean():.4f}")
