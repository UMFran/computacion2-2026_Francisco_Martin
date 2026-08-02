"""Proceso Recolector: centraliza el descubrimiento de procesos.

Cada `intervalo` segundos lista los PIDs vivos de /proc y reparte esa lista a
cada analizador por su propia Queue. Así el "qué procesos hay" se lee UNA sola
vez por ciclo (acá), en vez de que los 7 analizadores lo listen cada uno por su
cuenta. Los analizadores siguen leyendo /proc, pero solo para los DATOS de su
dimensión, sobre los PIDs que este proceso les repartió.
"""
import time

import procfs


def correr(intervalo, colas):
    """intervalo: segundos entre listados. colas: una Queue por analizador."""
    while True:
        pids = procfs.listar_pids()
        for cola in colas:
            cola.put(pids)          # reparte la lista actual a cada analizador
        time.sleep(intervalo)
