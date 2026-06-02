#!/usr/bin/env python3
"""Explorar los métodos de Pool."""
from multiprocessing import Pool
import time
import random

def cuadrado(x):
    """Tarea con duración variable para apreciar las diferencias."""
    duracion = random.uniform(0.1, 1.0)
    time.sleep(duracion)
    return x ** 2

def suma(a, b):
    return a + b

if __name__ == "__main__":
    with Pool(4) as pool:
        # map: síncrono, ordenado, bloquea hasta tener todo
        print("== map ==")
        print(pool.map(cuadrado, range(8)))

        # map_async: igual pero asíncrono
        print("\n== map_async ==")
        async_result = pool.map_async(cuadrado, range(8))
        print(f"ready inmediatamente? {async_result.ready()}")
        print(f"resultados: {async_result.get()}")

        # imap: iterador lazy, mantiene orden
        print("\n== imap (mantiene orden) ==")
        for r in pool.imap(cuadrado, range(8)):
            print(f"  llegó: {r}")

        # imap_unordered: lazy, sin orden (más rápido)
        print("\n== imap_unordered (orden de finalización) ==")
        for r in pool.imap_unordered(cuadrado, range(8)):
            print(f"  llegó: {r}")

        # starmap: función con múltiples argumentos
        print("\n== starmap ==")
        print(pool.starmap(suma, [(1, 2), (3, 4), (5, 6)]))

        # apply_async: control fino sobre tareas individuales
        print("\n== apply_async ==")
        resultado = pool.apply_async(cuadrado, (10,))
        print(f"ready? {resultado.ready()}")
        print(f"resultado: {resultado.get()}")

"""
Preguntas para reflexionar:

¿Por qué imap_unordered puede ser más rápido que imap en la práctica?
¿Cuándo conviene usar apply_async en lugar de map?
¿Qué pasaría si la duración de las tareas fuera constante?

Respuestas
imap_unordered puede ser más rápido porque devuelve resultados tan pronto como están listos, sin esperar a preservar el orden de entrada.
apply_async conviene cuando quieres enviar tareas individuales y recolectar resultados de forma asíncrona, o usar callbacks, en lugar de procesar un lote fijo con map.
Si la duración de las tareas fuera constante, imap e imap_unordered tenderían a producir resultados con el mismo orden y la ventaja de imap_unordered disminuiría.
"""