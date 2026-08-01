import argparse
import os
from pathlib import Path

def crear_parser():
    parser = argparse.ArgumentParser(description="Detecta enlaces simbólicos rotos.")
    parser.add_argument("directorio", help="Directorio donde buscar")
    parser.add_argument("--delete", action="store_true",
                        help="Ofrecer borrar los enlaces rotos (con confirmación)")
    parser.add_argument("--quiet",  action="store_true",
                        help="Solo mostrar el conteo")
    return parser

def buscar_rotos(directorio):
    """Devuelve lista de (ruta_link, destino) de symlinks rotos."""
    rotos = []
    ruta_base = Path(directorio)

    if not ruta_base.exists():
        print(f"Error: no existe '{directorio}'")
        return []

    for elemento in ruta_base.rglob("*"):
        try:
            # is_symlink() → es un symlink
            # exists()     → el DESTINO existe (sigue el link)
            # Si es symlink pero el destino no existe → está roto
            if elemento.is_symlink() and not elemento.exists():
                destino = os.readlink(elemento)  # a dónde apunta
                rotos.append((elemento, destino))
        except (PermissionError, OSError):
            continue

    return rotos

def main():
    parser = crear_parser()
    args = parser.parse_args()

    if not args.quiet:
        print(f"Buscando enlaces simbólicos rotos en {args.directorio}...\n")

    rotos = buscar_rotos(args.directorio)

    if args.quiet:
        print(len(rotos))
        return

    if not rotos:
        print("No se encontraron enlaces rotos.")
        return

    print("Enlaces rotos encontrados:")
    for ruta, destino in rotos:
        print(f"  {ruta} -> {destino} (no existe)")

    print(f"\nTotal: {len(rotos)} enlaces rotos")

    if args.delete:
        print()
        for ruta, destino in rotos:
            resp = input(f"¿Eliminar {ruta}? [s/N] ")
            if resp.lower() == "s":
                ruta.unlink()  # unlink() borra el symlink (no el destino)
                print(f"  Eliminado: {ruta}")
            else:
                print(f"  Saltado: {ruta}")

if __name__ == "__main__":
    main()