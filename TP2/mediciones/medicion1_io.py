#!/usr/bin/env python3
"""Medicion 1: concurrencia de I/O.

20 descargas secuenciales contra 20 concurrentes, y el speedup.

Mide la tecnica de descarga, no la API: es la diferencia entre un `for`
con `await` adentro y un `asyncio.gather`, que es lo mismo que hace la
tarea `descargar` por dentro. Base: clase20/descargas.py.

Uso (desde TP2/):
    python -m mediciones.medicion1_io
"""
import asyncio
import statistics
import sys
import time

import httpx

from .comun import fila, servidor, titulo

URLS = 20
DEMORA = 0.5           # segundos que tarda cada descarga
PUERTO = 8001


async def bajar(cliente, url):
    t0 = time.perf_counter()
    r = await cliente.get(url)
    return time.perf_counter() - t0, r.status_code, len(r.content)


async def secuencial(cliente, urls):
    """Un for con await adentro: espera cada una antes de pedir la siguiente."""
    return [await bajar(cliente, u) for u in urls]


async def concurrente(cliente, urls):
    """gather: las lanza todas y despues espera al conjunto."""
    return await asyncio.gather(*(bajar(cliente, u) for u in urls))


async def con_limite(cliente, urls, limite):
    """Como lo hace la tarea `descargar`: concurrente pero acotado."""
    sem = asyncio.Semaphore(limite)

    async def acotada(u):
        async with sem:
            return await bajar(cliente, u)

    return await asyncio.gather(*(acotada(u) for u in urls))


async def main():
    base = f'http://127.0.0.1:{PUERTO}'
    urls = [f'{base}/lento?s={DEMORA}&bytes=2048' for _ in range(URLS)]

    titulo(f'MEDICION 1: {URLS} descargas de {DEMORA}s contra un servidor local')
    print(f'  Cota teorica: secuencial = {URLS * DEMORA:.1f}s '
          f'(la suma), concurrente = {DEMORA:.1f}s (la mas lenta)')
    print()

    async with httpx.AsyncClient(timeout=60) as cliente:
        # Un pedido de calentamiento: la primera conexion paga el handshake
        # y el arranque del servidor, y no es parte de lo que queremos medir.
        await bajar(cliente, urls[0])

        resultados = {}
        for nombre, corrutina in [
            ('secuencial (for + await)', secuencial(cliente, urls)),
            ('concurrente (gather)', concurrente(cliente, urls)),
            ('concurrente, semaforo de 10', con_limite(cliente, urls, 10)),
            ('concurrente, semaforo de 5', con_limite(cliente, urls, 5)),
        ]:
            t0 = time.perf_counter()
            datos = await corrutina
            total = time.perf_counter() - t0
            individuales = [d[0] for d in datos]
            resultados[nombre] = total
            fila(nombre,
                 f'{total:6.2f}s   cada una: {statistics.mean(individuales):.3f}s '
                 f'(peor {max(individuales):.3f}s)')

    print()
    sec = resultados['secuencial (for + await)']
    con = resultados['concurrente (gather)']
    fila('SPEEDUP (secuencial / gather)', f'{sec / con:.1f}x')
    fila('overhead sobre la cota teorica', f'{con - DEMORA:.2f}s')
    print()
    print('  Interpretacion:')
    print(f'  - El secuencial da la suma de las {URLS} esperas porque `await`')
    print('    significa "espera esto": en un bucle, espera una por una.')
    print('  - El gather las lanza todas antes de esperar, asi que el total')
    print('    tiende al de la mas lenta, no a la suma.')
    print(f'  - El speedup NO es {URLS}x: lo acota el overhead que no')
    print('    desaparece (conexiones, parseo de las respuestas, el propio')
    print('    scheduling del loop). El techo es la relacion entre la suma')
    print('    de las esperas y la espera mas larga, no la cantidad de URLs.')
    print('  - Con semaforo el tiempo sube: es el precio de no abrir 20')
    print('    conexiones de golpe. Es lo que usa la tarea `descargar`.')


if __name__ == '__main__':
    with servidor('mediciones.servidor_lento:app', PUERTO):
        asyncio.run(main())
