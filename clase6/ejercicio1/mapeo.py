#!/usr/bin/env python3
"""Crear un archivo, mapearlo y modificarlo con mmap."""
import mmap

# Crear archivo con contenido
with open("/tmp/mmap_test.txt", "wb") as f:
    f.write(b"Linea 1: Hola mundo\n")
    f.write(b"Linea 2: Computacion II\n")
    f.write(b"Linea 3: mmap es genial\n")

# Mapear el archivo
with open("/tmp/mmap_test.txt", "r+b") as f:
    mm = mmap.mmap(f.fileno(), 0)

    # Leer todo el contenido
    print("=== Contenido completo ===")
    print(mm[:].decode())

    # Leer línea por línea
    print("=== Línea por línea ===")
    mm.seek(0)
    while True:
        linea = mm.readline()
        if not linea:
            break
        print(f"  {linea.decode().strip()}")

    # Buscar texto
    pos = mm.find(b"mmap")
    print(f"\n'mmap' encontrado en posición: {pos}")

    # Modificar una parte
    mm.seek(pos)
    mm.write(b"MMAP")  # Sobrescribir en mayúsculas

    # Ver resultado
    mm.seek(0)
    print(f"\n=== Después de modificar ===")
    print(mm[:].decode())

    mm.close()