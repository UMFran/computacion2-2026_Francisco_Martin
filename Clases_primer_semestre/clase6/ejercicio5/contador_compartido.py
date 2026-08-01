#!/usr/bin/env python3
"""
Demostración de race condition con Value.
Ejecutalo varias veces y observá cómo cambia el resultado.
"""
from multiprocessing import Process, Value
import time

def incrementar(contador, n, nombre):
    """Incrementa el contador n veces."""
    print(f"[{nombre}] Iniciando {n} incrementos...")
    for _ in range(n):
        contador.value += 1
    print(f"[{nombre}] Terminado")

# Crear valor compartido
contador = Value('i', 0)

# Lanzar 4 procesos que incrementan
N = 100000
procesos = []
for i in range(4):
    p = Process(target=incrementar, args=(contador, N, f"P{i}"))
    p.start()
    procesos.append(p)

for p in procesos:
    p.join()

esperado = 4 * N
print(f"\nEsperado: {esperado}")
print(f"Obtenido: {contador.value}")
print(f"Diferencia: {esperado - contador.value} (incrementos perdidos)")