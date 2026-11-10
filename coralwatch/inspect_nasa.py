from pathlib import Path
import xarray as xr

# Caminho dos arquivos NASA
DATA_DIR = Path("data/raw/nasa")

# Localizar arquivos NetCDF
nc_files = sorted(DATA_DIR.glob("*.nc"))

print(f"Total de arquivos encontrados: {len(nc_files)}")

# Explorar cada arquivo
for file_path in nc_files:

    print("\n" + "=" * 60)
    print(f"ARQUIVO: {file_path.name}")
    print("=" * 60)

    try:
        # Abrir apenas a estrutura e os metadados
        # Não carrega todos os dados na memória
        with xr.open_dataset(
            file_path,
            decode_cf=False,
            mask_and_scale=False
        ) as ds:

            # Dimensões
            print("\nDIMENSÕES:")
            for dimension, size in ds.sizes.items():
                print(f"{dimension}: {size}")

            # Variáveis disponíveis
            print("\nVARIÁVEIS:")

            for variable_name, variable in ds.data_vars.items():

                print(f"\nNome: {variable_name}")
                print(f"Dimensões: {variable.dims}")
                print(f"Formato: {variable.shape}")
                print(f"Tipo: {variable.dtype}")

                if "long_name" in variable.attrs:
                    print(f"Descrição: {variable.attrs['long_name']}")

                if "units" in variable.attrs:
                    print(f"Unidade: {variable.attrs['units']}")

            # Metadados gerais
            print("\nMETADADOS GERAIS:")
            for key, value in ds.attrs.items():
                print(f"{key}: {value}")

    except Exception as error:
        print(f"Erro ao abrir arquivo: {error}")