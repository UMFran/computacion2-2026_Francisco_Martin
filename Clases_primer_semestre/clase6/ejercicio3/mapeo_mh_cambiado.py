#!/usr/bin/env python3
"""Varios hijos calculan sumas parciales en regiones separadas del mmap."""
import mmap
import os
import struct

NUM_HIJOS = 4
NUMEROS_POR_HIJO = 25          # cada hijo suma 25 números
TAMAÑO_POR_HIJO = 64
TAMAÑO_TOTAL = NUM_HIJOS * TAMAÑO_POR_HIJO

mm = mmap.mmap(-1, TAMAÑO_TOTAL)

hijos = []
for i in range(NUM_HIJOS):
    pid = os.fork()
    if pid == 0:
        # Hijo: calcular rango y sumar
        inicio = i * NUMEROS_POR_HIJO + 1          # ej: hijo 0 → 1,  hijo 1 → 26
        fin    = inicio + NUMEROS_POR_HIJO - 1     # ej: hijo 0 → 25, hijo 1 → 50
        suma   = sum(range(inicio, fin + 1))

        # Escribir en su región
        offset = i * TAMAÑO_POR_HIJO
        struct.pack_into('i', mm, offset,     i)            # id del hijo
        struct.pack_into('i', mm, offset + 4, os.getpid()) # PID
        struct.pack_into('i', mm, offset + 8, inicio)      # inicio del rango
        struct.pack_into('i', mm, offset + 12, fin)        # fin del rango
        struct.pack_into('i', mm, offset + 16, suma)       # resultado

        print(f"  Hijo {i} (PID {os.getpid()}): suma({inicio}..{fin}) = {suma}")
        os._exit(0)
    else:
        hijos.append(pid)

# Padre espera a todos los hijos
for pid in hijos:
    os.waitpid(pid, 0)

# Leer resultados y calcular suma total
print("\n=== Resultados leídos por el padre ===")
suma_total = 0

for i in range(NUM_HIJOS):
    offset = i * TAMAÑO_POR_HIJO
    hijo_id  = struct.unpack_from('i', mm, offset)[0]
    hijo_pid = struct.unpack_from('i', mm, offset + 4)[0]
    inicio   = struct.unpack_from('i', mm, offset + 8)[0]
    fin      = struct.unpack_from('i', mm, offset + 12)[0]
    suma     = struct.unpack_from('i', mm, offset + 16)[0]

    suma_total += suma
    print(f"  Región {i}: id={hijo_id}, pid={hijo_pid}, "
          f"rango={inicio}..{fin}, suma_parcial={suma}")

# Verificación matemática: suma de 1 a N = N*(N+1)/2
n = NUM_HIJOS * NUMEROS_POR_HIJO
esperado = n * (n + 1) // 2

print(f"\n  Suma total (padre):   {suma_total}")
print(f"  Valor esperado (1..{n}): {esperado}")
print(f"  ¿Correcto? {'✓' if suma_total == esperado else '✗'}")

mm.close()