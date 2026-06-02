#!/usr/bin/env python3
"""Padre e hijo se comunican vía mmap anónimo."""
import mmap
import os
import struct
import time

# Crear mmap anónimo
mm = mmap.mmap(-1, 256)

pid = os.fork()

if pid == 0:
    # === HIJO ===
    print(f"[HIJO {os.getpid()}] Escribiendo datos...")

    # Escribir un entero
    struct.pack_into('i', mm, 0, 42)

    # Escribir un string
    mensaje = b"Hola desde el hijo!"
    struct.pack_into('i', mm, 4, len(mensaje))  # largo
    mm[8:8+len(mensaje)] = mensaje

    print("[HIJO] Datos escritos, terminando")
    os._exit(0)

else:
    # === PADRE ===
    os.wait()
    print(f"[PADRE] Hijo terminó, leyendo datos...")

    # Leer entero
    numero = struct.unpack_from('i', mm, 0)[0]
    print(f"[PADRE] Número: {numero}")

    # Leer string
    largo = struct.unpack_from('i', mm, 4)[0]
    mensaje = bytes(mm[8:8+largo]).decode()
    print(f"[PADRE] Mensaje: {mensaje}")

    mm.close()