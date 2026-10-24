#!/usr/bin/env python3
"""La cola, el registro de tareas y el pool de workers.

Es el corazon del sistema y el mismo patron que Clases_segundo_semestre/
clase21/cola.py: una asyncio.Queue, N corrutinas worker en bucle infinito,
y task_done() en un finally.

La diferencia con el ejemplo de la clase es que aca la cola lleva solo el
`id` de la tarea, no la tarea entera. Asi hay UNA sola fuente de verdad (el
dict `registro`): si el DELETE marca una tarea como cancelada mientras
todavia esta en la cola, el worker lo ve cuando la saca.
"""
import asyncio
import logging
import time
import uuid
from concurrent.futures import ProcessPoolExecutor

from . import modelos
from . import tareas

log = logging.getLogger('gestor')

CANTIDAD_WORKERS = 2        # configurable: es el "pool de workers" de la consigna
TAMANO_COLA = 100           # maxsize: control de flujo, no optimizacion
MAX_PROCESOS = 2            # procesos para las tareas CPU-bound

# Estado del sistema. Vive en memoria, como pide la consigna (sin base de datos).
cola = None                 # se crea en arrancar(): asyncio.Queue necesita un loop
pool = None                 # ProcessPoolExecutor para las tareas CPU-bound
registro = {}               # id -> ficha de la tarea
workers = []                # los asyncio.Task de los workers


# ---------------------------------------------------------------- arranque

def arrancar():
    """Crea la cola y lanza los workers. Lo llama el lifespan de main.py.

    No se puede hacer a nivel de modulo: asyncio.Queue y create_task
    necesitan un event loop ya corriendo, y al importarse el modulo todavia
    no hay ninguno.
    """
    global cola, pool
    cola = asyncio.Queue(maxsize=TAMANO_COLA)

    # El pool se crea UNA vez, no por tarea: arrancar un proceso cuesta
    # cargar un interprete entero, y hacerlo en cada hash anularia la
    # ganancia (clase 22, "Crear el pool una vez").
    pool = ProcessPoolExecutor(max_workers=MAX_PROCESOS)

    for i in range(CANTIDAD_WORKERS):
        workers.append(asyncio.create_task(worker(i)))
    log.info('pool arrancado: %d workers, %d procesos, cola de %d',
             CANTIDAD_WORKERS, MAX_PROCESOS, TAMANO_COLA)


async def detener():
    """Apaga los workers por cancelacion.

    return_exceptions=True porque cancelar un Task hace que await lance
    CancelledError: sin eso, el gather explotaria en el primero.

    En E4 esto se convierte en el apagado ordenado de verdad (centinela +
    volcado a JSON). Por ahora corta y listo.
    """
    for w in workers:
        w.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
    workers.clear()

    # wait=False para no colgar el apagado esperando a un hash que puede
    # tardar minutos. cancel_futures descarta lo que todavia no arranco.
    # Lo que YA arranco en un proceso hijo no se puede interrumpir: queda
    # como limitacion conocida para el README.
    pool.shutdown(wait=False, cancel_futures=True)
    log.info('pool detenido')


# ------------------------------------------------------------------ worker

async def worker(wid):
    """Bucle infinito: saca una tarea de la cola y la ejecuta.

    Tres cosas que no son casualidad:

    1. `await cola.get()`: si la cola esta vacia SUSPENDE esta corrutina, no
       bloquea el hilo. Una queue.Queue congelaria el servidor entero cada
       vez que no hay trabajo.
    2. `while True`: el worker no termina nunca. Vive mientras viva la app y
       lo apaga detener().
    3. `task_done()` en finally: si falta, el join() del apagado espera para
       siempre (clase 21).
    """
    while True:
        tid = await cola.get()
        try:
            await ejecutar_una(tid)
        finally:
            cola.task_done()


async def ejecutar_una(tid):
    """Ejecuta una tarea y deja su resultado en la ficha."""
    ficha = registro[tid]

    # Pudieron cancelarla mientras esperaba en la cola: no hay Task que
    # cancelar, el DELETE solo marco la ficha. Aca la descartamos.
    if ficha['estado'] == modelos.CANCELADA:
        log.info('tarea %s venia cancelada, se descarta', tid)
        return

    # Este bloque no tiene ningun await adentro, asi que ninguna otra
    # corrutina puede ver la ficha a medio actualizar. Por eso no hace falta
    # un Lock (clase 11 vs clase 20).
    ficha['estado'] = modelos.EJECUTANDO
    ficha['inicio'] = time.time()

    try:
        ficha['resultado'] = await tareas.ejecutar(ficha['tipo'],
                                                   ficha['parametros'], pool)
        ficha['estado'] = modelos.COMPLETADA
    except Exception as e:
        # except Exception, NO except BaseException: CancelledError hereda de
        # BaseException justamente para que un except generico no se la trague
        # (clase 22). Asi una tarea que falla no mata al worker, pero una
        # cancelacion sigue propagando.
        ficha['estado'] = modelos.FALLIDA
        ficha['motivo'] = f'{type(e).__name__}: {e}'
        log.warning('tarea %s fallo: %s', tid, ficha['motivo'])
    finally:
        ficha['fin'] = time.time()


# --------------------------------------------------------------- operaciones

def encolar(pedido):
    """Crea la ficha y mete el id en la cola. NO espera a que se ejecute.

    put_nowait y no `await put()`: con la cola llena, await put() dejaria al
    POST esperando, y la consigna exige que responda inmediatamente. Asi
    lanza QueueFull y main.py lo traduce a un 503 honesto.
    """
    tid = uuid.uuid4().hex[:8]
    ficha = modelos.crear_ficha(tid, pedido)
    cola.put_nowait(tid)            # lanza asyncio.QueueFull si esta llena
    registro[tid] = ficha
    return ficha


def obtener(tid):
    """La ficha de una tarea, o None si ese id no existe."""
    return registro.get(tid)


def listar(estado=None):
    """Todas las fichas, o solo las de un estado."""
    fichas = list(registro.values())
    if estado is not None:
        fichas = [f for f in fichas if f['estado'] == estado]
    return fichas
