#!/usr/bin/env python3
"""Mapear archivo en modo solo lectura."""
import mmap

# Asegurate de tener el archivo del ejercicio anterior
with open("/tmp/mmap_test.txt", "rb") as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

    # Esto funciona:
    print(f"Contenido: {mm[:40]}")
    print(f"Tamaño: {mm.size()} bytes")

    # Esto lanza excepción:
    try:
        mm[0:4] = b"TEST"
    except TypeError as e:
        print(f"Error al escribir: {e}")

    mm.close()