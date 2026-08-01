#!/usr/bin/env python3
"""Usar mmap como almacenamiento binario estructurado."""
import mmap
import struct
import os

ARCHIVO = "/tmp/registros.bin"

# Formato: entero (id) + float (nota) + 20 bytes (nombre)
FORMATO = 'i f 20s'
TAMAÑO_REGISTRO = struct.calcsize(FORMATO)  # tamaño de un registro en bytes
NUM_REGISTROS = 5
TAMAÑO_TOTAL = NUM_REGISTROS * TAMAÑO_REGISTRO

# Datos de ejemplo
registros = [
    (1, 9.5,  "Ana García"),
    (2, 7.3,  "Bruno López"),
    (3, 8.1,  "Carla Díaz"),
    (4, 6.0,  "Diego Ruiz"),
    (5, 10.0, "Elena Torres"),
]

# Crear archivo con tamaño fijo
with open(ARCHIVO, "wb") as f:
    f.write(b'\x00' * TAMAÑO_TOTAL)

with open(ARCHIVO, "r+b") as f:
    mm = mmap.mmap(f.fileno(), TAMAÑO_TOTAL)

    # Escribir registros
    print(f"Tamaño por registro: {TAMAÑO_REGISTRO} bytes")
    print(f"Tamaño total: {TAMAÑO_TOTAL} bytes\n")

    print("Escribiendo registros...")
    for i, (id_, nota, nombre) in enumerate(registros):
        offset = i * TAMAÑO_REGISTRO
        nombre_bytes = nombre.encode('utf-8')   # texto → bytes
        struct.pack_into(FORMATO, mm, offset, id_, nota, nombre_bytes)
        print(f"  [{i}] id={id_}, nota={nota}, nombre='{nombre}'")

    # Leer todos los registros
    print("\nLeyendo registros...")
    for i in range(NUM_REGISTROS):
        offset = i * TAMAÑO_REGISTRO
        id_, nota, nombre_bytes = struct.unpack_from(FORMATO, mm, offset)
        nombre = nombre_bytes.decode('utf-8').rstrip('\x00')  # bytes → texto
        print(f"  [{i}] id={id_}, nota={nota:.1f}, nombre='{nombre}'")

    # Modificar el registro en posición 2
    print("\nModificando registro en posición 2...")
    offset = 2 * TAMAÑO_REGISTRO
    struct.pack_into(FORMATO, mm, offset, 99, 5.5, b'Modificado')
    id_, nota, nombre_bytes = struct.unpack_from(FORMATO, mm, offset)
    nombre = nombre_bytes.decode('utf-8').rstrip('\x00')
    print(f"  Nuevo valor: id={id_}, nota={nota:.1f}, nombre='{nombre}'")

    mm.close()

os.unlink(ARCHIVO)