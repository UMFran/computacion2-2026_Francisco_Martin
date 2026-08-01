#!/usr/bin/env python3
"""mmap compartido con multiprocessing.Process."""
import mmap
import struct
from multiprocessing import Process
import os

def worker(mm_fileno, offset, datos):
    """Worker que escribe datos en el mmap compartido."""
    # Nota: no podemos pasar el objeto mmap directamente,
    # pero con fork el hijo hereda el mmap del padre
    pass

# Con fork, los hijos heredan el mmap automáticamente
# Pero es más limpio usar una variable global o compartida

# Enfoque con archivo compartido:
ARCHIVO = "/tmp/mmap_mp.bin"
TAMAÑO = 256

with open(ARCHIVO, "wb") as f:
    f.write(b'\x00' * TAMAÑO)

def escribir_en_mmap(archivo, offset, mensaje):
    """Cada proceso abre el archivo y escribe."""
    with open(archivo, "r+b") as f:
        mm = mmap.mmap(f.fileno(), TAMAÑO)
        encoded = mensaje.encode()
        struct.pack_into('i', mm, offset, len(encoded))
        mm[offset+4:offset+4+len(encoded)] = encoded
        mm.close()

procesos = []
mensajes = [
    "Hola desde proceso 0",
    "Saludos del proceso 1",
    "Proceso 2 presente",
    "Proceso 3 reportando",
]

for i, msg in enumerate(mensajes):
    p = Process(target=escribir_en_mmap, args=(ARCHIVO, i * 64, msg))
    p.start()
    procesos.append(p)

for p in procesos:
    p.join()

# Leer resultados
with open(ARCHIVO, "r+b") as f:
    mm = mmap.mmap(f.fileno(), TAMAÑO)
    print("=== Mensajes de los procesos ===")
    for i in range(4):
        offset = i * 64
        largo = struct.unpack_from('i', mm, offset)[0]
        if largo > 0:
            msg = bytes(mm[offset+4:offset+4+largo]).decode()
            print(f"  Proceso {i}: {msg}")
    mm.close()

os.unlink(ARCHIVO)