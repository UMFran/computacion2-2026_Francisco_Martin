#!/usr/bin/env python3
"""Ejercicio 3: Procesamiento paralelo por fases con Barrier."""
import threading
import time
import random

NUM_WORKERS = 4
datos = [0] * NUM_WORKERS
resultados_fase1 = [0] * NUM_WORKERS
resultados_fase2 = [0] * NUM_WORKERS


def imprimir_estado():
    print(f"  Resultados fase 1: {resultados_fase1}")
    print(f"  Resultados fase 2: {resultados_fase2}")


barrera = threading.Barrier(NUM_WORKERS, action=imprimir_estado)


def worker(id):
    global datos, resultados_fase1, resultados_fase2

    # Fase 1: procesar datos locales
    print(f"[Worker {id}] Fase 1: procesando...")
    time.sleep(random.uniform(0.5, 1.5))
    resultados_fase1[id] = datos[id] * 2
    print(f"[Worker {id}] Fase 1: completada")

    barrera.wait()  # Sincronizar

    # Fase 2: combinar con vecinos
    print(f"[Worker {id}] Fase 2: combinando...")
    time.sleep(random.uniform(0.3, 0.8))
    vecino = (id + 1) % NUM_WORKERS
    resultados_fase2[id] = resultados_fase1[id] + resultados_fase1[vecino]
    print(f"[Worker {id}] Fase 2: completada")

    barrera.wait()  # Sincronizar

    print(f"[Worker {id}] Procesamiento completo!")


if __name__ == "__main__":
    # Inicializar datos
    datos = [i * 10 for i in range(NUM_WORKERS)]
    print(f"Datos iniciales: {datos}\n")

    threads = [threading.Thread(target=worker, args=(i,))
               for i in range(NUM_WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\nResultados finales: {resultados_fase2}")
