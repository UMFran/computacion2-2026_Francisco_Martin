import argparse
import os
from pathlib import Path

def crear_parser():
    parser = argparse.ArgumentParser(description="Busca archivos grandes en un directorio.")
    parser.add_argument("directorio", help="Directorio donde buscar")
    parser.add_argument("--min-size", default="1M",
                        help="Tamaño mínimo (ej: 100K, 1M, 2G). Default: 1M")
    parser.add_argument("--type", choices=["f", "d"], dest="tipo",
                        help="Tipo: f=archivos, d=directorios")
    parser.add_argument("--top", type=int, metavar="N",
                        help="Mostrar solo los N más grandes")
    return parser

def parsear_tamano(texto):
    """
    Convierte "1M" → 1048576, "100K" → 102400, "2G" → 2147483648.
    Si no tiene sufijo, asume bytes.
    """
    sufijos = {"K": 1024, "M": 1024**2, "G": 1024**3}
    texto = texto.strip().upper()
    if texto[-1] in sufijos:
        return int(texto[:-1]) * sufijos[texto[-1]]
    return int(texto)

def formato_tamano(bytes):
    """Muestra el tamaño en la unidad más legible."""
    if bytes >= 1024**3:
        return f"{bytes / 1024**3:.1f} GB"
    elif bytes >= 1024**2:
        return f"{bytes / 1024**2:.1f} MB"
    elif bytes >= 1024:
        return f"{bytes / 1024:.1f} KB"
    return f"{bytes} bytes"

def buscar(directorio, min_bytes, tipo):
    """Recorre recursivamente y devuelve lista de (tamaño, ruta)."""
    resultados = []
    ruta_base = Path(directorio)

    if not ruta_base.exists():
        print(f"Error: no existe '{directorio}'")
        return []
    if not ruta_base.is_dir():
        print(f"Error: '{directorio}' no es un directorio")
        return []

    # rglob("*") recorre todos los archivos y carpetas de forma recursiva
    for elemento in ruta_base.rglob("*"):
        try:
            # Filtrar por tipo si se pidió
            if tipo == "f" and not elemento.is_file():
                continue
            if tipo == "d" and not elemento.is_dir():
                continue

            tamanio = elemento.stat().st_size
            if tamanio >= min_bytes:
                resultados.append((tamanio, elemento))
        except (PermissionError, OSError):
            # Algunos archivos del sistema no se pueden leer, los salteamos
            continue

    # Ordenar de mayor a menor
    resultados.sort(reverse=True)
    return resultados

def main():
    parser = crear_parser()
    args = parser.parse_args()

    try:
        min_bytes = parsear_tamano(args.min_size)
    except ValueError:
        print(f"Error: tamaño inválido '{args.min_size}'. Usá formatos como 100K, 1M, 2G")
        return

    resultados = buscar(args.directorio, min_bytes, args.tipo)

    if not resultados:
        print("No se encontraron archivos que cumplan los criterios.")
        return

    if args.top:
        print(f"Los {args.top} archivos más grandes:")
        for i, (tamanio, ruta) in enumerate(resultados[:args.top], 1):
            print(f"  {i}. {ruta} ({formato_tamano(tamanio)})")
    else:
        for tamanio, ruta in resultados:
            print(f"{ruta} ({formato_tamano(tamanio)})")

    # Resumen final
    total_archivos = len(resultados)
    total_bytes    = sum(t for t, _ in resultados)
    print(f"\nTotal: {total_archivos} archivos, {formato_tamano(total_bytes)}")

if __name__ == "__main__":
    main()