#!/usr/bin/env python3
"""Utilidades compartidas por los tres scripts de medicion."""
import contextlib
import subprocess
import sys
import time

import httpx


@contextlib.contextmanager
def servidor(modulo, puerto, entorno=None):
    """Levanta un uvicorn en un subproceso y lo baja al salir.

    Un subproceso y no un thread: asi el servidor tiene su propio event
    loop y su propio GIL, y no contamina lo que estamos midiendo del lado
    del cliente. `entorno` permite barrer TP2_WORKERS y TP2_PROCESOS sin
    tocar el codigo (medicion 3).
    """
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', modulo,
         '--host', '127.0.0.1', '--port', str(puerto), '--log-level', 'error'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=entorno)
    try:
        esperar_listo(puerto)
        yield f'http://127.0.0.1:{puerto}'
    finally:
        proc.terminate()            # SIGTERM: el apagado ordenado
        try:
            proc.wait(timeout=25)
        except subprocess.TimeoutExpired:
            proc.kill()


def esperar_listo(puerto, limite=30):
    """Espera a que el puerto responda. Sin esto se mide el arranque."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite:
        try:
            httpx.get(f'http://127.0.0.1:{puerto}/docs', timeout=1)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f'el servidor del puerto {puerto} no arranco')


def titulo(texto):
    print()
    print('=' * 68)
    print(texto)
    print('=' * 68)


def fila(etiqueta, *valores):
    print('  %-34s %s' % (etiqueta, '  '.join(str(v) for v in valores)))


def esperar_tarea(cliente, tid, limite=300):
    """Espera a que una tarea llegue a un estado final y devuelve la ficha."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite:
        f = cliente.get(f'/tareas/{tid}').json()
        if f['estado'] in ('completada', 'fallida', 'cancelada'):
            return f
        time.sleep(0.05)
    raise RuntimeError(f'la tarea {tid} no termino en {limite}s')
