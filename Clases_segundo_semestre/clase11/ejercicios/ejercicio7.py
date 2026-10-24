#!/usr/bin/env python3
"""Ejercicio 7: Filósofos comensales, del deadlock a la solución.

    python3 ejercicio7.py --a    # se cuelga SIEMPRE (cortar con Ctrl+C)
    python3 ejercicio7.py --b    # jerarquía de recursos
    python3 ejercicio7.py --c    # semáforo de N-1 comensales
    python3 ejercicio7.py --d    # comparación (corre B y C y mide)
"""
import sys
import threading
import time
import random

NUM = 5
COMIDAS = 3


# ---- Parte A: la versión que se cuelga ----
# Cada filósofo toma primero su tenedor izquierdo, después el derecho.
# La Barrier fuerza el estado que produce el deadlock: nadie pide el
# derecho hasta que todos tengan el izquierdo.

def parte_a():
    tenedores = [threading.Lock() for _ in range(NUM)]
    tomaron_izq = threading.Barrier(NUM)

    def filosofo_ingenuo(id):
        for _ in range(COMIDAS):
            izq, der = id, (id + 1) % NUM
            with tenedores[izq]:
                tomaron_izq.wait()        # los 5 ya tienen su izquierdo
                with tenedores[der]:      # ...y ninguno consigue el derecho
                    print(f"Filósofo {id} come")

    print("Parte A: esto se cuelga siempre. Cortar con Ctrl+C.")
    hilos = [threading.Thread(target=filosofo_ingenuo, args=(i,), daemon=True)
             for i in range(NUM)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()


# ---- Parte B: jerarquía de recursos ----
# Cada filósofo toma siempre primero el tenedor de MENOR índice.
# Se ordenan los ÍNDICES, no los objetos Lock.

def filosofo_jerarquia(id, tenedores, comidas, esperas):
    for _ in range(COMIDAS):
        izq, der = id, (id + 1) % NUM
        primero, segundo = min(izq, der), max(izq, der)
        inicio = time.perf_counter()
        with tenedores[primero]:
            with tenedores[segundo]:
                esperas[id] += time.perf_counter() - inicio
                comidas[id] += 1
                time.sleep(random.uniform(0.01, 0.05))


# ---- Parte C: limitar comensales ----
# Versión ingenua (izquierdo primero) pero con un Semaphore(NUM - 1):
# como mucho 4 filósofos intentan comer a la vez.

def filosofo_semaforo(id, tenedores, semaforo, comidas, esperas):
    for _ in range(COMIDAS):
        izq, der = id, (id + 1) % NUM
        inicio = time.perf_counter()
        with semaforo:
            with tenedores[izq]:
                with tenedores[der]:
                    esperas[id] += time.perf_counter() - inicio
                    comidas[id] += 1
                    time.sleep(random.uniform(0.01, 0.05))


def correr(nombre, objetivo, usa_semaforo=False):
    """Corre una solución y devuelve (segundos, comidas, esperas)."""
    tenedores = [threading.Lock() for _ in range(NUM)]
    comidas = [0] * NUM
    esperas = [0.0] * NUM
    semaforo = threading.Semaphore(NUM - 1)

    if usa_semaforo:
        args = lambda i: (i, tenedores, semaforo, comidas, esperas)
    else:
        args = lambda i: (i, tenedores, comidas, esperas)

    hilos = [threading.Thread(target=objetivo, args=args(i)) for i in range(NUM)]
    inicio = time.perf_counter()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    total = time.perf_counter() - inicio

    print(f"--- {nombre} ---")
    print(f"  tiempo total: {total:.3f}s")
    print(f"  comidas por filósofo: {comidas}")
    print(f"  espera acumulada por filósofo: "
          f"{[f'{e:.3f}' for e in esperas]}")
    print()
    return total, comidas, esperas


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--a" in args:
        parte_a()
    elif "--b" in args:
        correr("Parte B: jerarquía de recursos", filosofo_jerarquia)
    elif "--c" in args:
        correr("Parte C: semáforo de N-1", filosofo_semaforo, usa_semaforo=True)
    else:
        # Parte D: comparación
        correr("Parte B: jerarquía de recursos", filosofo_jerarquia)
        correr("Parte C: semáforo de N-1", filosofo_semaforo, usa_semaforo=True)
        print("Las dos completan las 3 comidas por filósofo: no hay deadlock.")
        print("La espera acumulada es la que muestra si alguno comió peor.")
