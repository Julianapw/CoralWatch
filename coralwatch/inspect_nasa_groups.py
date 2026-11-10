
from pathlib import Path
from netCDF4 import Dataset

# Caminho dos arquivos NASA
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "nasa"

# Atributos que queremos investigar
IMPORTANT_ATTRIBUTES = [
    "long_name",
    "standard_name",
    "units",
    "description",
    "flag_values",
    "flag_meanings",
    "valid_min",
    "valid_max",
]


def inspect_group(group, group_path="/"):

    print(f"\nGRUPO: {group_path}")

    # 1. Dimensões
    print("\nDimensões:")

    if group.dimensions:
        for name, dimension in group.dimensions.items():
            print(f"  {name}: {len(dimension)}")
    else:
        print("  Nenhuma dimensão neste grupo.")

    # 2. Variáveis
    print("\nVariáveis:")

    if group.variables:
        for name, variable in group.variables.items():

            print(f"\n  Nome: {name}")
            print(f"  Dimensões: {variable.dimensions}")
            print(f"  Formato: {variable.shape}")
            print(f"  Tipo: {variable.dtype}")

            for attribute in IMPORTANT_ATTRIBUTES:
                if attribute in variable.ncattrs():
                    value = variable.getncattr(attribute)
                    print(f"  {attribute}: {value}")

    else:
        print("  Nenhuma variável neste grupo.")

    # 3. Investigar grupos internos
    if group.groups:

        print("\nSubgrupos encontrados:")

        for subgroup_name, subgroup in group.groups.items():

            print(f"  - {subgroup_name}")

            inspect_group(
                subgroup,
                group_path=f"{group_path}{subgroup_name}/"
            )


def main():

    files = sorted(DATA_DIR.glob("*.nc"))

    if not files:
        print("Nenhum arquivo NetCDF encontrado!")
        return

    print(f"Total de arquivos: {len(files)}")

    for file_path in files:

        print("\n" + "=" * 70)
        print(f"ARQUIVO: {file_path.name}")
        print("=" * 70)

        try:
            # Abrir apenas a estrutura do arquivo.
            # Não carregar os dados na memória.
            with Dataset(file_path, mode="r") as nc:

                print("\nGrupos na raiz:", list(nc.groups.keys()))

                inspect_group(nc)

        except Exception as error:
            print(f"Erro ao investigar arquivo: {error}")


if __name__ == "__main__":
    main()
