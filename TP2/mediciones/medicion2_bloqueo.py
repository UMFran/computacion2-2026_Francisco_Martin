#!/usr/bin/env python3
"""Medicion 2: el event loop bloqueado.

Corre una tarea CPU-bound pesada SIN run_in_executor y mide cuanto tarda
en responder un GET /tareas durante ese lapso. Despues lo repite CON
executor. La diferencia es el punto de la materia.

Mide la API de verdad, desde afuera del proceso del servidor: es la
latencia que veria un cliente. Base: clase21/executor.py, que mide el
atraso del propio event loop.

Uso (desde TP2/):
    python -m mediciones.medicion2_bloqueo
"""
import statistics
import time

import httpx

from .comun import fila, servidor, titulo

ITERACIONES = 12_000_000     # ~5s de CPU en la maquina donde se midio
PUERTO = 8000


def calibrar(cliente):
    """Mide cuanto tarda el calculo, para saber contra que comparamos."""
    tid = cliente.post('/tareas', json={
        'tipo': 'hashear',
        'parametros': {'texto': 'calibracion', 'iteraciones': ITERACIONES},
        'timeout': 300,
    }).json()['id']
    while True:
        f = cliente.get(f'/tareas/{tid}').json()
        if f['estado'] in ('completada', 'fallida'):
            return f['resultado']['segundos']
        time.sleep(0.1)


def medir(cliente, sin_executor):
    """Encola un hash pesado y mide la latencia de GET /tareas mientras corre.

    Cada GET se cronometra individualmente. Si el event loop esta
    bloqueado, el pedido no se atiende hasta que se libere: la latencia de
    ESE GET es lo que la consigna pide reportar.
    """
    tid = cliente.post('/tareas', json={
        'tipo': 'hashear',
        'parametros': {
            'texto': 'medicion',
            'iteraciones': ITERACIONES,
            'sin_executor': sin_executor,
        },
        'timeout': 300,
    }).json()['id']

    # Un respiro para que un worker lo saque de la cola y arranque.
    time.sleep(0.3)

    latencias = []
    t0 = time.perf_counter()
    while True:
        t1 = time.perf_counter()
        r = cliente.get('/tareas')
        latencias.append((time.perf_counter() - t1) * 1000)
        if r.json()['total'] and cliente.get(f'/tareas/{tid}').json()['estado'] \
                in ('completada', 'fallida'):
            break
        time.sleep(0.1)

    pared = time.perf_counter() - t0
    ficha = cliente.get(f'/tareas/{tid}').json()
    return {
        'calculo': ficha['resultado']['segundos'],
        'pared': pared,
        'gets': len(latencias),
        'peor': max(latencias),
        'media': statistics.mean(latencias),
    }


def main():
    base = f'http://127.0.0.1:{PUERTO}'
    with httpx.Client(base_url=base, timeout=300) as cliente:
        titulo('MEDICION 2: el event loop bloqueado')
        print(f'  Tarea: hashear {ITERACIONES:,} iteraciones de SHA-256')
        dur = calibrar(cliente)
        print(f'  Calibracion: el calculo tarda {dur:.2f}s')
        print()

        sin = medir(cliente, sin_executor=True)
        con = medir(cliente, sin_executor=False)

        print('  %-22s %10s %10s %8s %12s' %
              ('', 'calculo', 'GETs', 'peor GET', 'GET medio'))
        for etiqueta, m in [('SIN run_in_executor', sin),
                            ('CON run_in_executor', con)]:
            print('  %-22s %9.2fs %10d %7.0fms %11.1fms' %
                  (etiqueta, m['calculo'], m['gets'], m['peor'], m['media']))

        print()
        fila('el calculo tardo', f"{sin['calculo']:.2f}s sin executor, "
                                 f"{con['calculo']:.2f}s con executor")
        fila('la API se degrado', f"{sin['peor'] / con['peor']:.0f}x "
                                  f"({sin['peor']:.0f}ms contra {con['peor']:.0f}ms)")
        print()
        print('  Interpretacion:')
        print('  - SIN executor el GET no se atiende hasta que el calculo')
        print('    termina: el event loop es UN SOLO HILO y la corrutina que')
        print('    calcula no tiene ningun await donde ceder el control. No')
        print('    es contencion: es que nunca devuelve el control.')
        print('  - Por eso durante el calculo entra UN solo GET (el que')
        print('    quedo encolado) en vez de decenas.')
        print('  - CON executor el calculo tarda LO MISMO. El executor no')
        print('    acelera nada: lo unico que cambia es que el resto del')
        print('    sistema sigue vivo. Asyncio es sobre aprovechamiento, no')
        print('    sobre velocidad.')
        print('  - Durante ese lapso, SIN executor tampoco se dispararia')
        print('    ningun timeout ni avanzaria ningun otro worker.')


if __name__ == '__main__':
    with servidor('app.main:app', PUERTO):
        main()
