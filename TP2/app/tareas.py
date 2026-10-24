#!/usr/bin/env python3
"""Las funciones de trabajo.

Este modulo no sabe que existe una cola, ni un worker, ni una API: recibe
parametros y devuelve un resultado. Eso lo hace facil de probar suelto
desde el interprete.

Las tres tareas no estan elegidas al azar, cada una ejercita algo distinto:
  esperar   -> I/O simulado: cancelacion y timeouts
  descargar -> I/O-bound: concurrencia asincrona real
  hashear   -> CPU-bound: la prueba de que asyncio NO sirve para esto
"""
import asyncio
import hashlib
import time

import httpx

# Cuantas descargas como maximo en vuelo a la vez DENTRO de una tarea.
# Sin esto, una tarea con 10.000 URLs abre 10.000 conexiones de golpe y
# agota los descriptores de archivo del proceso (clase 20).
MAX_DESCARGAS_SIMULTANEAS = 10

TIMEOUT_HTTP = 10


# --------------------------------------------------------------- esperar

async def esperar(segundos):
    """Duerme N segundos sin bloquear el event loop.

    asyncio.sleep y no time.sleep: time.sleep duerme EL HILO, y el hilo es
    el del event loop (clase 18). Ademas la cancelacion se entrega en un
    await, asi que una tarea hecha con time.sleep seria incancelable.
    """
    await asyncio.sleep(segundos)
    return {'dormido': segundos}


# ------------------------------------------------------------- descargar

async def _bajar(cliente, url, sem):
    """Una descarga. Devuelve codigo de estado, tamano y cuanto tardo."""
    async with sem:                     # async with, no with: adquirir puede esperar
        t0 = time.perf_counter()
        r = await cliente.get(url)      # await: suspende, no bloquea
        return {
            'url': url,
            'estado_http': r.status_code,
            'bytes': len(r.content),
            'segundos': round(time.perf_counter() - t0, 3),
        }


async def descargar(urls):
    """Baja todas las URLs CONCURRENTEMENTE.

    Dos decisiones que van al README:

    1. gather y no un `for url in urls: await bajar(url)`. El for seria
       secuencial: el total serla la SUMA de las descargas. Con gather las
       lanza todas y el total tiende a la MAS LENTA (clase 18).

    2. UN solo AsyncClient para todas, no uno por URL. El cliente mantiene
       un pool de conexiones y las reutiliza (keep-alive, clase 19). Uno
       por URL pagaria el handshake de TCP -y de TLS- en cada una.

    El `async with` del cliente tambien resuelve la cancelacion limpia: si
    cancelan la tarea a mitad de las descargas, el CancelledError propaga
    por el __aexit__ y las conexiones abiertas se cierran solas.
    """
    sem = asyncio.Semaphore(MAX_DESCARGAS_SIMULTANEAS)

    async with httpx.AsyncClient(timeout=TIMEOUT_HTTP,
                                 follow_redirects=True) as cliente:
        # return_exceptions=True: una URL caida no tiene que tirar abajo a
        # las otras 19. Sin esto, la primera excepcion cancela el resto.
        crudos = await asyncio.gather(
            *(_bajar(cliente, u, sem) for u in urls),
            return_exceptions=True)

    # gather devuelve en el orden en que se PASARON, no en el que
    # terminaron, asi que el zip con `urls` empareja bien.
    resultados = []
    for url, r in zip(urls, crudos):
        if isinstance(r, Exception):
            resultados.append({'url': url, 'error': f'{type(r).__name__}: {r}'})
        else:
            resultados.append(r)
    return resultados


# --------------------------------------------------------------- hashear

def hashear_bloqueante(texto, iteraciones):
    """SHA-256 aplicado N veces. CPU-bound puro: no cede el control a nadie.

    Es sincronica y esta a nivel de modulo A PROPOSITO: el
    ProcessPoolExecutor la manda al proceso hijo por pickle, y para eso
    tiene que ser importable por nombre. Una lambda o una funcion anidada
    no se pueden picklear (clase 22).

    Si esto se llamara directo desde una corrutina, con N grande congelaria
    el servidor entero: no hay ningun await donde el loop pueda recuperar
    el control.
    """
    h = texto.encode()
    for _ in range(iteraciones):
        h = hashlib.sha256(h).digest()
    return h.hex()


async def hashear(texto, iteraciones, pool):
    """Calcula el hash iterado FUERA del event loop.

    run_in_executor manda la funcion al pool de procesos y devuelve algo
    que se puede esperar. Desde aca se ve como cualquier otro await: la
    corrutina se suspende y el loop se va a atender a todos los demas
    (clase 21).

    Ojo: el calculo tarda LO MISMO. El executor no acelera nada, solo evita
    que bloquee a los otros. Eso es lo que mide la medicion 2.

    run_in_executor solo pasa argumentos posicionales; para keyword habria
    que envolver en functools.partial.
    """
    loop = asyncio.get_running_loop()
    t0 = time.perf_counter()
    digest = await loop.run_in_executor(pool, hashear_bloqueante,
                                        texto, iteraciones)
    return {
        'hash': digest,
        'iteraciones': iteraciones,
        'segundos': round(time.perf_counter() - t0, 3),
    }


# -------------------------------------------------------------- despacho

async def ejecutar(tipo, parametros, pool):
    """Despacha al tipo de tarea que corresponda.

    Un tipo desconocido no deberia llegar nunca -Pydantic lo rechaza con
    422 en el POST- pero si llega preferimos una excepcion clara antes que
    un None silencioso.
    """
    if tipo == 'esperar':
        return await esperar(float(parametros.get('segundos', 1)))

    if tipo == 'descargar':
        urls = parametros.get('urls') or []
        if not urls:
            raise ValueError('descargar necesita parametros.urls con al menos una URL')
        return await descargar(urls)

    if tipo == 'hashear':
        texto = parametros.get('texto', '')
        iteraciones = int(parametros.get('iteraciones', 100_000))
        return await hashear(texto, iteraciones, pool)

    raise ValueError(f'tipo de tarea desconocido: {tipo}')
