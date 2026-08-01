#!/usr/bin/env python3
"""Cálculo paralelo de math.sin con Array compartido y race condition en Value."""
from multiprocessing import Process, Array, Value
import math
import time

def calcular_seno(resultado, suma_compartida, inicio, fin, nombre):
    """Calcula math.sin(i * 0.01) para el rango [inicio, fin)."""
    print(f"[{nombre}] Calculando índices {inicio}..{fin - 1}")
    
    suma_local = 0.0
    for i in range(inicio, fin):
        valor = math.sin(i * 0.01)
        resultado[i] = valor
        suma_local += valor

    # Bonus: acumular en Value compartido → race condition intencional
    suma_compartida.value += suma_local

    print(f"[{nombre}] Suma parcial local: {suma_local:.6f}")

# ── Configuración ──────────────────────────────────────────────
TAMAÑO       = 100
NUM_PROCESOS = 4
chunk        = TAMAÑO // NUM_PROCESOS

resultado       = Array('d', TAMAÑO)       # doubles compartidos
suma_compartida = Value('d', 0.0)          # acumulador compartido (con race condition)

# ── Lanzar procesos ────────────────────────────────────────────
inicio_t = time.time()

procesos = []
for i in range(NUM_PROCESOS):
    ini = i * chunk
    fin = (i + 1) * chunk if i < NUM_PROCESOS - 1 else TAMAÑO
    p = Process(
        target=calcular_seno,
        args=(resultado, suma_compartida, ini, fin, f"P{i}")
    )
    p.start()
    procesos.append(p)

for p in procesos:
    p.join()

duracion = time.time() - inicio_t

# ── Mostrar primeros 20 resultados ─────────────────────────────
print(f"\n=== Primeros 20 resultados ===")
for i in range(20):
    print(f"  sin({i} * 0.01) = sin({i * 0.01:.2f}) = {resultado[i]:.6f}")

# ── Bonus: comparar suma compartida vs suma correcta ───────────
suma_correcta = sum(math.sin(i * 0.01) for i in range(TAMAÑO))

print(f"\n=== Bonus: race condition en Value ===")
print(f"  Suma correcta (padre):     {suma_correcta:.6f}")
print(f"  Suma compartida (procesos): {suma_compartida.value:.6f}")
print(f"  Diferencia:                 {abs(suma_correcta - suma_compartida.value):.6f}")

race = abs(suma_correcta - suma_compartida.value) > 1e-9
print(f"  ¿Race condition detectada? {'⚠ Sí' if race else '✓ No (tuviste suerte)'}")

print(f"\nTiempo total: {duracion:.4f}s")