#!/usr/bin/env python3
"""La cola, el registro de tareas y el pool de workers.

Es el corazon del sistema y el mismo patron que Clases_segundo_semestre/
clase21/cola.py: una asyncio.Queue, N corrutinas worker en bucle infinito,
y task_done() en un finally.

Dos diferencias con el ejemplo de la clase:

1. La cola lleva solo el `id` de la tarea, no la tarea entera. Asi hay UNA
   sola fuente de verdad (el dict `registro`): si el DELETE marca una tarea
   como cancelada mientras todavia esta en la cola, el worker lo ve cuando
   la saca.

2. El worker no ejecuta la tarea directo con `await`, sino que la envuelve
   en un asyncio.Task aparte. Es lo que permite cancelar UNA TAREA sin
   matar al worker que la estaba corriendo.
"""
import asyncio
import glob
import json
import logging
import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor

from . import modelos
from . import tareas

log = logging.getLogger('gestor')

# Configurables por variable de entorno, para poder barrerlos en la
# medicion 3 sin tocar el codigo. Los valores por omision son los que usa
# el docker-compose.
CANTIDAD_WORKERS = int(os.environ.get('TP2_WORKERS', 2))
TAMANO_COLA = int(os.environ.get('TP2_COLA', 100))
MAX_PROCESOS = int(os.environ.get('TP2_PROCESOS', 2))
ESPERA_APAGADO = int(os.environ.get('TP2_ESPERA_APAGADO', 10))
DIR_ESTADOS = os.environ.get('TP2_DIR_ESTADOS', 'estados')

# Marca de "no hay mas trabajo". Es un object() y no un string para que no
# pueda confundirse nunca con el id de una tarea (clase 21).
CENTINELA = object()

# Estado del sistema. Vive en memoria, como pide la consigna (sin base de datos).
cola = None                 # se crea en arrancar(): asyncio.Queue necesita un loop
pool = None                 # ProcessPoolExecutor para las tareas CPU-bound
registro = {}               # id -> ficha de la tarea
workers = []                # los asyncio.Task de los workers
ejecutando = {}             # id -> asyncio.Task de la tarea que esta corriendo
aceptando = True            # se apaga al recibir la senal: no mas tareas nuevas

# Ids que el DELETE pidio cancelar. Sirve para que el worker distinga una
# cancelacion de TAREA (sigue vivo) de una cancelacion del WORKER (se va).
# Sin esto las dos llegan como el mismo CancelledError y no se pueden
# diferenciar.
cancelados_por_delete = set()


# ---------------------------------------------------------------- arranque

def arrancar():
    """Crea la cola y el pool, y lanza los workers. Lo llama el lifespan.

    No se puede hacer a nivel de modulo: asyncio.Queue y create_task
    necesitan un event loop ya corriendo, y al importarse el modulo todavia
    no hay ninguno.
    """
    global cola, pool, aceptando
    reportar_volcado_previo()

    aceptando = True
    cola = asyncio.Queue(maxsize=TAMANO_COLA)

    # El pool se crea UNA vez, no por tarea: arrancar un proceso cuesta
    # cargar un interprete entero, y hacerlo en cada hash anularia la
    # ganancia (clase 22, "Crear el pool una vez").
    pool = ProcessPoolExecutor(max_workers=MAX_PROCESOS)

    for i in range(CANTIDAD_WORKERS):
        workers.append(asyncio.create_task(worker(i)))
    log.info('pool arrancado: %d workers, %d procesos, cola de %d',
             CANTIDAD_WORKERS, MAX_PROCESOS, TAMANO_COLA)


async def apagar():
    """Apagado ordenado. Lo dispara el lifespan al recibir SIGTERM/SIGINT.

    Los cuatro pasos que pide la consigna, en orden:

      1. dejar de aceptar tareas nuevas
      2. esperar a las que estan en curso, CON LIMITE
      3. volcar el estado a estado_<timestamp>.json
      4. (al arrancar) reportar si habia un volcado previo

    Para el paso 2 se usa primero el CENTINELA y despues la cancelacion
    como plan B, que son las dos formas que muestra clase21/cola.py:

      - Centinela: un marcador por worker. Cada uno termina la tarea que
        tiene entre manos y recien despues sale. Ninguna queda a medias.
      - Cancelacion: corta en el proximo await. Es lo que se usa si se
        agoto la espera.
    """
    global aceptando
    aceptando = False
    log.info('apagado: dejo de aceptar tareas nuevas')

    # Un centinela POR worker: cada uno consume el suyo y se retira.
    for _ in workers:
        try:
            cola.put_nowait(CENTINELA)
        except asyncio.QueueFull:
            pass            # si no entra, el plan B se encarga

    try:
        await asyncio.wait_for(asyncio.gather(*workers), ESPERA_APAGADO)
        log.info('los %d workers salieron ordenadamente', len(workers))
    except TimeoutError:
        # wait_for ya cancelo el gather, que cancelo a los workers. Solo
        # queda recogerlos. return_exceptions=True porque cada uno va a
        # lanzar CancelledError.
        pendientes = cola.qsize()
        log.warning('se agoto la espera de %ss: corto por cancelacion '
                    '(%d tareas quedaron sin procesar)',
                    ESPERA_APAGADO, pendientes)
        await asyncio.gather(*workers, return_exceptions=True)

    workers.clear()

    # wait=False para no colgar el apagado esperando a un hash que puede
    # tardar minutos. cancel_futures descarta lo que todavia no arranco.
    # Lo que YA arranco en un proceso hijo no se puede interrumpir: queda
    # como limitacion conocida para el README.
    pool.shutdown(wait=False, cancel_futures=True)

    ruta = volcar_estado()
    log.info('estado volcado en %s', ruta)


# ------------------------------------------------------------- persistencia

def volcar_estado():
    """Escribe el registro completo a estados/estado_<timestamp>.json.

    Que la ficha de una tarea sea un dict y no un objeto Pydantic paga
    justamente aca: ya es JSON, no hay que serializar nada a mano.
    """
    os.makedirs(DIR_ESTADOS, exist_ok=True)
    ruta = os.path.join(DIR_ESTADOS,
                        f'estado_{time.strftime("%Y%m%d_%H%M%S")}.json')
    volcado = {
        'momento': time.strftime('%Y-%m-%d %H:%M:%S'),
        'estadisticas': estadisticas(),
        'tareas': registro,
    }
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(volcado, f, indent=2, ensure_ascii=False)
    return ruta


def reportar_volcado_previo():
    """Si hay volcados de una corrida anterior, los reporta por log.

    La consigna pide reportarlo, no recargarlo: el estado NO se restaura.
    El volcado es para inspeccion despues del apagado.
    """
    previos = sorted(glob.glob(os.path.join(DIR_ESTADOS, 'estado_*.json')))
    if not previos:
        log.info('no hay volcados previos')
        return
    ultimo = previos[-1]
    try:
        with open(ultimo, encoding='utf-8') as f:
            tareas_previas = len(json.load(f).get('tareas', {}))
        log.info('volcado previo encontrado: %s (%d tareas). '
                 'Hay %d volcado(s) en total. No se restaura el estado.',
                 ultimo, tareas_previas, len(previos))
    except (OSError, ValueError) as e:
        log.warning('hay un volcado previo en %s pero no se pudo leer: %s',
                    ultimo, e)


# ------------------------------------------------------------------ worker

async def worker(wid):
    """Bucle infinito: saca una tarea de la cola y la ejecuta.

    La tarea se ejecuta en un Task APARTE (no con un await directo) para
    que el DELETE pueda cancelarla sin matar a este worker. Si hicieramos
    `await ejecutar_una(tid)`, el unico Task cancelable seria el worker.

    Entre que `cola.get()` devuelve el id y que lo guardamos en
    `ejecutando` no hay ningun await, asi que el DELETE no puede caer en el
    medio: o encuentra la tarea en la cola, o la encuentra en `ejecutando`.
    Nunca en un limbo. Esa es la misma propiedad por la que no hace falta
    un Lock (clase 20).
    """
    while True:
        tid = await cola.get()

        # El centinela del apagado ordenado: este worker ya termino la
        # tarea que tenia, asi que se retira sin dejar nada a medias.
        if tid is CENTINELA:
            cola.task_done()
            log.info('worker %d se retira ordenadamente', wid)
            return

        try:
            tarea_actual = asyncio.create_task(ejecutar_una(tid))
            ejecutando[tid] = tarea_actual
            try:
                await tarea_actual
            except asyncio.CancelledError:
                if tid not in cancelados_por_delete:
                    raise           # nos cancelaron al WORKER: nos vamos
                # Cancelaron la TAREA: el worker sigue con la siguiente.
                cancelados_por_delete.discard(tid)
                log.info('tarea %s cancelada, worker %d sigue vivo', tid, wid)
        finally:
            ejecutando.pop(tid, None)
            cola.task_done()        # SIEMPRE, o join() espera para siempre


async def ejecutar_una(tid):
    """Ejecuta una tarea y deja su resultado en la ficha."""
    ficha = registro[tid]

    # Pudieron cancelarla mientras esperaba en la cola: no habia Task que
    # cancelar, el DELETE solo marco la ficha. Aca la descartamos.
    if ficha['estado'] == modelos.CANCELADA:
        log.info('tarea %s venia cancelada, se descarta', tid)
        return

    # Este bloque no tiene ningun await adentro, asi que ninguna otra
    # corrutina puede ver la ficha a medio actualizar. Por eso no hace
    # falta un Lock (clase 11 vs clase 20).
    ficha['estado'] = modelos.EJECUTANDO
    ficha['inicio'] = time.time()

    try:
        # asyncio.timeout CANCELA lo de adentro al vencer: un timeout es
        # una cancelacion con reloj, no un mecanismo aparte (clase 20).
        async with asyncio.timeout(ficha['timeout']):
            ficha['resultado'] = await tareas.ejecutar(ficha['tipo'],
                                                       ficha['parametros'], pool)
        ficha['estado'] = modelos.COMPLETADA

    except TimeoutError:
        ficha['estado'] = modelos.FALLIDA
        ficha['motivo'] = f'timeout de {ficha["timeout"]}s'
        log.warning('tarea %s vencio por timeout', tid)

    except asyncio.CancelledError:
        # Si vino del DELETE, cancelar() ya marco la ficha. Si vino del
        # apagado, la marcamos aca.
        if ficha['estado'] != modelos.CANCELADA:
            ficha['estado'] = modelos.CANCELADA
            ficha['motivo'] = 'cancelada por apagado'
        raise                       # SIEMPRE relanzarla (clase 20)

    except Exception as e:
        # except Exception, NO except BaseException: CancelledError hereda
        # de BaseException justamente para que un except generico no se la
        # trague (clase 22). Asi una tarea que falla no mata al worker,
        # pero una cancelacion sigue propagando.
        ficha['estado'] = modelos.FALLIDA
        ficha['motivo'] = f'{type(e).__name__}: {e}'
        log.warning('tarea %s fallo: %s', tid, ficha['motivo'])

    finally:
        ficha['fin'] = time.time()


# --------------------------------------------------------------- operaciones

def encolar(pedido):
    """Crea la ficha y mete el id en la cola. NO espera a que se ejecute.

    put_nowait y no `await put()`: con la cola llena, await put() dejaria
    al POST esperando, y la consigna exige que responda inmediatamente.
    Asi lanza QueueFull y main.py lo traduce a un 503 honesto.
    """
    tid = uuid.uuid4().hex[:8]
    ficha = modelos.crear_ficha(tid, pedido)
    cola.put_nowait(tid)            # lanza asyncio.QueueFull si esta llena
    registro[tid] = ficha
    return ficha


def cancelar(tid):
    """Cancela una tarea. Devuelve desde que estado se la cancelo.

    Hay dos situaciones completamente distintas:

    - La tarea todavia espera en la cola: NO hay Task que cancelar. Solo se
      marca la ficha, y el worker la descarta cuando la saque.

    - La tarea esta corriendo: se busca su Task en `ejecutando` y se le hace
      cancel(). Eso NO la mata: le pide al loop que, en su proximo await,
      le lance CancelledError en vez del resultado. Por eso una tarea sin
      awaits por delante -un hashear que ya arranco en un proceso hijo- no
      se entera: queda marcada cancelada pero el proceso sigue calculando.
    """
    ficha = registro[tid]
    ficha['estado'] = modelos.CANCELADA
    ficha['fin'] = time.time()

    tarea = ejecutando.get(tid)
    if tarea is None:
        ficha['motivo'] = 'cancelada mientras esperaba en la cola'
        return modelos.PENDIENTE

    ficha['motivo'] = 'cancelada en ejecucion'
    cancelados_por_delete.add(tid)
    tarea.cancel()
    return modelos.EJECUTANDO


def obtener(tid):
    """La ficha de una tarea, o None si ese id no existe."""
    return registro.get(tid)


def listar(estado=None):
    """Todas las fichas, o solo las de un estado."""
    fichas = list(registro.values())
    if estado is not None:
        fichas = [f for f in fichas if f['estado'] == estado]
    return fichas


def estadisticas():
    """Totales por estado, tiempos promedio y ocupacion del pool."""
    fichas = list(registro.values())

    por_estado = {e: 0 for e in modelos.ESTADOS}
    for f in fichas:
        por_estado[f['estado']] += 1

    # Solo las que alcanzaron a arrancar y terminar tienen tiempos medibles.
    medibles = [f for f in fichas if f['inicio'] and f['fin']]

    def promedio(valores):
        return round(sum(valores) / len(valores), 3) if valores else None

    return {
        'total': len(fichas),
        'por_estado': por_estado,
        'promedio_espera_en_cola': promedio([f['inicio'] - f['encolada']
                                             for f in medibles]),
        'promedio_ejecucion': promedio([f['fin'] - f['inicio']
                                        for f in medibles]),
        'workers': {
            'total': CANTIDAD_WORKERS,
            # Un worker esta ocupado exactamente cuando tiene una tarea en
            # `ejecutando`: el dict ya es el contador.
            'ocupados': len(ejecutando),
        },
        'cola': {
            'encoladas': cola.qsize() if cola else 0,
            'maxsize': TAMANO_COLA,
        },
    }
