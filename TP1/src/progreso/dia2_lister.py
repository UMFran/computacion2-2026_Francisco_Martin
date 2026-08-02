"""Día 2 (standalone) — Orquestador multiproceso con datos de PRUEBA.

Es el esqueleto del Día 2 preservado: arquitectura de procesos + IPC + snapshot
compartido funcionando de punta a punta, pero cada analizador devuelve un
contador de prueba (stub) en vez de leer /proc. Sirve para ver la arquitectura
pura (y para la demo de kill -9) sin el ruido de los datos reales.

Para la versión con los 7 analizadores reales + señales, usá main.py.
"""
import multiprocessing as mp
import time

from analizadores import base

ANALIZADORES = {
    "resumen": 2.0,
    "memoria": 3.0,
    "fds": 5.0,
    "threads": 2.0,
    "senales": 10.0,
    "scheduling": 10.0,
    "sistema": 2.0,
}


def construir_snapshot(manager):
    snapshot = manager.dict()
    for nombre in ANALIZADORES:
        snapshot[nombre] = {"datos": {}, "ts": 0.0}
    return snapshot


def lanzar_analizadores(snapshot, lock):
    componentes = {}
    for nombre, intervalo_def in ANALIZADORES.items():
        intervalo = mp.Value("d", intervalo_def)
        p = mp.Process(
            target=base.correr,
            args=(nombre, snapshot, lock, intervalo, base.stub_recolectar(nombre)),
            name=f"analizador-{nombre}",
        )
        p.start()
        componentes[nombre] = (p, intervalo)
    return componentes


def imprimir_estado(snapshot, componentes):
    ahora = time.time()
    print("=" * 78)
    for nombre, (p, intervalo) in componentes.items():
        entrada = snapshot[nombre]
        ts = entrada["ts"]
        edad = (ahora - ts) if ts else float("inf")
        vivo = "VIVO  " if p.is_alive() else "MUERTO"
        print(f"{nombre:<11} pid={p.pid:<6} {vivo} "
              f"cada={intervalo.value:4.1f}s  actualizado_hace={edad:5.1f}s  "
              f"datos={entrada['datos']}")


def main():
    manager = mp.Manager()
    snapshot = construir_snapshot(manager)
    lock = mp.Lock()
    componentes = lanzar_analizadores(snapshot, lock)
    try:
        while True:
            time.sleep(2)
            imprimir_estado(snapshot, componentes)
    except KeyboardInterrupt:
        print("\nCerrando... (shutdown limpio real está en main.py, Día 3)")
    finally:
        for p, _ in componentes.values():
            p.terminate()
        for p, _ in componentes.values():
            p.join()
        manager.shutdown()


if __name__ == "__main__":
    mp.set_start_method("fork")
    main()
