"""Día 3 (standalone) — Orquestador con supervisor de TEXTO (sin TUI).

Es la versión del Día 3 preservada: los 7 analizadores + señales, pero mostrando
el estado con prints de texto plano en vez de la TUI. Sirve para ver el progreso
"crudo" del snapshot sin curses/rich. La versión con TUI es main.py (Día 4).

Orquestador con los 7 analizadores reales + manejo de señales.

Arquitectura:
  - Manager().dict() = snapshot global (7 claves con {datos, ts}).
  - 7 procesos analizadores, cada uno con su Value('d') de intervalo.
  - lock compartido para coordinar el snapshot.
  - Value('i') `verbose` compartido (SIGUSR2 lo togglea).
  - handlers de señales que solo prenden flags; el loop principal actúa.
"""
import json
import multiprocessing as mp
import os
import time

import senales
from analizadores import (resumen, memoria, fds, threads,
                          senales as vista_senales, scheduling, sistema)

RAIZ = os.path.join(os.path.dirname(__file__), "..")
CONFIG = os.path.join(RAIZ, "config.json")

# nombre -> módulo analizador. El orden fija el orden de impresión.
MODULOS = {
    "resumen": resumen,
    "memoria": memoria,
    "fds": fds,
    "threads": threads,
    "senales": vista_senales,
    "scheduling": scheduling,
    "sistema": sistema,
}


def cargar_config():
    with open(CONFIG) as f:
        return json.load(f)


def construir_snapshot(manager):
    snapshot = manager.dict()
    for nombre in MODULOS:
        snapshot[nombre] = {"datos": {}, "ts": 0.0}
    return snapshot


def lanzar_analizadores(snapshot, lock, verbose, cfg):
    """Crea Values de intervalo y arranca los 7 procesos.
    Devuelve {nombre: (Process, Value_intervalo)}."""
    from analizadores import base
    componentes = {}
    for nombre, modulo in MODULOS.items():
        intervalo = mp.Value("d", cfg["intervalos"][nombre])
        recolectar = modulo.crear_recolector(verbose)
        p = mp.Process(
            target=base.correr,
            args=(nombre, snapshot, lock, intervalo, recolectar),
            name=f"analizador-{nombre}",
        )
        p.start()
        componentes[nombre] = (p, intervalo)
    return componentes


# --------------------------------------------------------------------------- #
# Acciones disparadas por señales (las ejecuta el loop, NO el handler)
# --------------------------------------------------------------------------- #
def recargar_config(componentes):
    """SIGHUP: relee config.json y actualiza los Value de intervalo en caliente."""
    try:
        cfg = cargar_config()
    except (OSError, json.JSONDecodeError) as e:
        print(f"[SIGHUP] no pude leer config.json: {e}")
        return
    for nombre, (_, intervalo) in componentes.items():
        nuevo = cfg["intervalos"].get(nombre)
        if nuevo:
            intervalo.value = float(nuevo)
    print(f"[SIGHUP] config recargada -> intervalos: "
          f"{ {n: round(v.value, 1) for n, (_, v) in componentes.items()} }")


def volcar_dump(snapshot):
    """SIGUSR1: guarda el snapshot actual a dump_<timestamp>.json."""
    ts = int(time.time())
    ruta = os.path.join(RAIZ, f"dump_{ts}.json")
    plano = {nombre: dict(entrada) for nombre, entrada in snapshot.items()}
    with open(ruta, "w") as f:
        json.dump(plano, f, indent=2, default=str)
    print(f"[SIGUSR1] snapshot volcado a {os.path.basename(ruta)}")


def toggle_verbose(verbose):
    """SIGUSR2: alterna el modo verbose (los analizadores lo leen del Value)."""
    verbose.value = 0 if verbose.value else 1
    print(f"[SIGUSR2] modo verbose {'ON' if verbose.value else 'OFF'}")


# --------------------------------------------------------------------------- #
def resumir(nombre, datos):
    if not datos:
        return "(sin datos aún)"
    if nombre == "resumen":
        procs = datos["procesos"]
        top = f"; top CPU {procs[0]['cmd'][:18]} {procs[0]['cpu']}%" if procs else ""
        return f"{datos['n']} procs{top}"
    if nombre == "fds":
        total = sum(p.get("total", 0) for p in datos["procesos"])
        return f"{datos['n']} procs, {total} FDs abiertos"
    if nombre == "threads":
        total = sum(len(p["hilos"]) for p in datos["procesos"])
        return f"{datos['n']} procs, {total} threads"
    if nombre == "sistema":
        c = datos.get("cpu", {})
        return (f"CPU u{c.get('user','?')}% s{c.get('system','?')}% "
                f"idle{c.get('idle','?')}% | load {datos['load'][0]} | "
                f"procs {datos['procesos_total']} (Z:{datos['zombies']}) | "
                f"thr {datos['threads_total']}")
    return f"{datos.get('n', '?')} procs"


def imprimir_estado(snapshot, componentes, verbose):
    ahora = time.time()
    print("=" * 92)
    print(f"  MONITOR  |  verbose={'ON' if verbose.value else 'OFF'}  |  "
          f"{time.strftime('%H:%M:%S')}")
    print("-" * 92)
    for nombre, (p, intervalo) in componentes.items():
        entrada = snapshot[nombre]
        ts = entrada["ts"]
        edad = (ahora - ts) if ts else float("inf")
        vivo = "VIVO  " if p.is_alive() else "MUERTO"
        print(f"{nombre:<11} {vivo} cada={intervalo.value:4.1f}s "
              f"hace={edad:4.1f}s | {resumir(nombre, entrada['datos'])}")


def main():
    cfg = cargar_config()
    manager = mp.Manager()
    snapshot = construir_snapshot(manager)
    lock = mp.Lock()
    verbose = mp.Value("i", 1 if cfg.get("verbose") else 0)

    componentes = lanzar_analizadores(snapshot, lock, verbose, cfg)

    estado = senales.EstadoSenales()
    senales.instalar(estado)
    print(f"Monitor arriba. PID={os.getpid()}. "
          f"Probá: kill -HUP/-USR1/-USR2/-TERM {os.getpid()}")

    try:
        while not estado.salir:
            # El loop consume los flags que prendieron los handlers.
            if estado.recargar:
                estado.recargar = False
                recargar_config(componentes)
            if estado.dump:
                estado.dump = False
                volcar_dump(snapshot)
            if estado.toggle_verbose:
                estado.toggle_verbose = False
                toggle_verbose(verbose)

            imprimir_estado(snapshot, componentes, verbose)
            time.sleep(1.0)  # tick corto: las señales se atienden en <=1s
    finally:
        print("\nShutdown: terminando analizadores...")
        for p, _ in componentes.values():
            p.terminate()
        for p, _ in componentes.values():
            p.join()
        manager.shutdown()
        print("Listo, salida limpia.")


if __name__ == "__main__":
    mp.set_start_method("fork")
    main()
