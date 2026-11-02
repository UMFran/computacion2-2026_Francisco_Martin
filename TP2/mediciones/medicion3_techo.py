#!/usr/bin/env python3
"""Medicion 3: el techo del pool.

Sube la cantidad de tareas concurrentes hasta que los tiempos se
degradan, y averigua DONDE esta el limite y POR QUE.

La respuesta no es un solo numero: hay varios cuellos de botella
distintos y cada uno se rompe de una forma distinta. El script los separa:

  A) tareas I/O-bound, pocos workers   -> el techo es CANTIDAD_WORKERS
  B) lo mismo con mas workers          -> el techo se corre
  C) tareas CPU-bound                  -> el techo son los procesos/nucleos
  D) rafaga mas grande que la cola     -> no degrada: rechaza con 503

Uso (desde TP2/):
    python -m mediciones.medicion3_techo
"""
import os
import statistics
import time

import httpx

from .comun import fila, servidor, titulo

PUERTO = 8000
DEMORA = 1.0                      # segundos de cada tarea I/O
CARGAS = (2, 4, 8, 16, 32, 64)


def rafaga(cliente, cantidad, tipo, parametros):
    """Encola `cantidad` tareas de golpe y espera a que terminen todas.

    Devuelve el tiempo de pared y las latencias extremo a extremo de cada
    tarea (desde que se encolo hasta que termino), que es lo que ve el
    cliente.
    """
    t0 = time.perf_counter()
    ids, rechazadas = [], 0
    for _ in range(cantidad):
        r = cliente.post('/tareas', json={'tipo': tipo,
                                          'parametros': parametros,
                                          'timeout': 300})
        if r.status_code == 201:
            ids.append(r.json()['id'])
        else:
            rechazadas += 1

    while True:
        e = cliente.get('/estadisticas').json()['por_estado']
        if e['pendiente'] == 0 and e['ejecutando'] == 0:
            break
        time.sleep(0.05)
    pared = time.perf_counter() - t0

    latencias, esperas = [], []
    for tid in ids:
        f = cliente.get(f'/tareas/{tid}').json()
        if f['inicio'] and f['fin']:
            latencias.append(f['fin'] - f['encolada'])
            esperas.append(f['inicio'] - f['encolada'])
    return pared, latencias, esperas, rechazadas


def barrido(cliente, titulo_barrido, tipo, parametros, cota):
    print(f'  {titulo_barrido}')
    print('  %6s %9s %12s %12s %12s' %
          ('tareas', 'pared', 'latencia med', 'espera med', 'cota teorica'))
    for n in CARGAS:
        pared, lat, esp, _ = rafaga(cliente, n, tipo, parametros)
        print('  %6d %8.2fs %11.2fs %11.2fs %11.2fs' %
              (n, pared, statistics.mean(lat), statistics.mean(esp), cota(n)))
    print()


def main():
    base = f'http://127.0.0.1:{PUERTO}'

    # ---- A y D: con la configuracion por omision (2 workers, cola de 100)
    with servidor('app.main:app', PUERTO):
        with httpx.Client(base_url=base, timeout=300) as c:
            titulo('MEDICION 3: el techo del pool')
            cfg = c.get('/estadisticas').json()
            print(f"  Configuracion: {cfg['workers']['total']} workers, "
                  f"cola de {cfg['cola']['maxsize']}")
            print()

            barrido(c, 'A) Tareas I/O-bound (esperar 1s) con 2 workers',
                    'esperar', {'segundos': DEMORA},
                    cota=lambda n: (n / 2) * DEMORA)

            print('  D) Rafaga mas grande que la cola (150 tareas, cola de 100)')
            pared, lat, esp, rech = rafaga(c, 150, 'esperar', {'segundos': 0.1})
            fila('aceptadas', 150 - rech)
            fila('rechazadas con 503', rech)
            print()

    # ---- B: el mismo barrido con 8 workers
    entorno = dict(os.environ, TP2_WORKERS='8')
    with servidor('app.main:app', PUERTO, entorno=entorno):
        with httpx.Client(base_url=base, timeout=300) as c:
            barrido(c, 'B) Las mismas tareas I/O-bound con 8 workers',
                    'esperar', {'segundos': DEMORA},
                    cota=lambda n: (n / 8) * DEMORA)

    # ---- C: CPU-bound, donde los workers ya no ayudan
    entorno = dict(os.environ, TP2_WORKERS='8', TP2_PROCESOS='2')
    with servidor('app.main:app', PUERTO, entorno=entorno):
        with httpx.Client(base_url=base, timeout=300) as c:
            print('  C) Tareas CPU-bound (hashear 4M) con 8 workers '
                  'pero solo 2 procesos')
            print('  %6s %9s %12s %12s' %
                  ('tareas', 'pared', 'latencia med', 'calculo med'))
            for n in (1, 2, 4, 8):
                pared, lat, esp, _ = rafaga(
                    c, n, 'hashear',
                    {'texto': 'techo', 'iteraciones': 4_000_000})
                calculos = [c.get('/tareas', params={'estado': 'completada'})
                            .json()['tareas'][-1]['resultado']['segundos']]
                print('  %6d %8.2fs %11.2fs %11.2fs' %
                      (n, pared, statistics.mean(lat), calculos[0]))
            print()

    print('  Interpretacion:')
    print('  - A) El techo NO es la cantidad de tareas: es CANTIDAD_WORKERS.')
    print('    Cada tarea sigue tardando 1s; lo que crece es la ESPERA EN')
    print('    COLA, lineal con tareas/workers. El sistema no se degrada,')
    print('    se encola: es el comportamiento correcto.')
    print('  - B) Con 8 workers el mismo trabajo sale ~4x mas rapido y la')
    print('    espera en cola casi desaparece. Subir workers es gratis')
    print('    mientras las tareas sean I/O-bound: no consumen CPU mientras')
    print('    esperan. Ese es todo el argumento de asyncio.')
    print('  - C) Con CPU-bound los workers dejan de servir: el cuello pasa')
    print('    a ser MAX_PROCESOS y los nucleos de la maquina. 8 workers no')
    print('    hacen nada si hay 2 procesos: las tareas hacen cola en el')
    print('    executor en vez de en la asyncio.Queue.')
    print('  - D) Pasado el maxsize no hay degradacion: hay RECHAZO con 503.')
    print('    Es deliberado. Con una cola infinita el sistema no fallaria')
    print('    rapido y claro, se degradaria lento hasta quedarse sin')
    print('    memoria.')
    print()
    print('  Si me mandan 10.000 tareas de golpe, lo primero que se rompe es')
    print('  la cola: 100 entran y 9.900 se rechazan con 503. Si la cola')
    print('  fuera infinita, el siguiente limite seria la memoria del')
    print('  registro, que guarda cada ficha con su resultado para siempre.')


if __name__ == '__main__':
    main()
