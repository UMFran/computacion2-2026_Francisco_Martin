#!/usr/bin/env python3
"""Map-Reduce para conteo de palabras."""
from functools import reduce
from multiprocessing import Pool
from pathlib import Path
import sys

TEXTOS = [
    "el rapido zorro marron salta sobre el perro perezoso",
    "el perro duerme bajo el arbol mientras el zorro corre",
    "rapido como el viento el zorro vuelve a saltar sobre el perro",
    "el arbol es viejo y el perro lo mira con curiosidad",
    "saltar correr el zorro y el perro juegan bajo el arbol",
]


def mapper(texto):
    """Cuenta palabras en un texto o chunk de texto (etapa map)."""
    conteo = {}
    for palabra in texto.lower().split():
        conteo[palabra] = conteo.get(palabra, 0) + 1
    return conteo


def reducer(dict1, dict2):
    """Combina dos diccionarios de conteo (etapa reduce)."""
    resultado = dict1.copy()
    for palabra, count in dict2.items():
        resultado[palabra] = resultado.get(palabra, 0) + count
    return resultado


def chunked_file(path, lines_per_chunk=1000):
    """Genera chunks de texto a partir de un archivo grande."""
    buffer = []
    with open(path, encoding="utf-8") as archivo:
        for linea in archivo:
            buffer.append(linea.strip())
            if len(buffer) >= lines_per_chunk:
                yield " ".join(buffer)
                buffer = []
        if buffer:
            yield " ".join(buffer)


def procesar_textos(textos, pool_size=4):
    """Map-Reduce paralelo para una lista o generador de textos."""
    conteo_total = {}
    with Pool(pool_size) as pool:
        for conteo_parcial in pool.imap(mapper, textos):
            conteo_total = reducer(conteo_total, conteo_parcial)
    return conteo_total


def imprimir_top(conteo_total, top_n=10):
    palabras_ordenadas = sorted(conteo_total.items(), key=lambda x: -x[1])
    print("Top palabras más frecuentes:")
    for palabra, count in palabras_ordenadas[:top_n]:
        print(f"  {palabra:15s} {count}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        archivo_path = Path(sys.argv[1])
        if not archivo_path.exists():
            print(f"Archivo no encontrado: {archivo_path}")
            sys.exit(1)
        textos = chunked_file(archivo_path, lines_per_chunk=1000)
        conteo_total = procesar_textos(textos)
        print(f"Procesado archivo grande: {archivo_path}")
    else:
        conteo_total = procesar_textos(TEXTOS)

    imprimir_top(conteo_total)
