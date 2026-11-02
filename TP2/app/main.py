#!/usr/bin/env python3
"""La API HTTP.

Los endpoints no saben COMO se ejecuta una tarea: encolan y leen fichas.
Todo el trabajo esta en gestor.py.

En E1 estan los tres primeros endpoints. DELETE /tareas/{id} y
GET /estadisticas se agregan en E3.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import gestor
from . import modelos

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(name)s: %(message)s')


@asynccontextmanager
async def ciclo(app):
    """Arranca y apaga el pool junto con la aplicacion.

    Es el esqueleto de la clase 21 ("Juntando todo: la arquitectura del
    TP2"). Antes del yield corre al arrancar, despues del yield al apagar.
    Es el unico lugar donde se puede crear la cola, porque recien aca hay un
    event loop corriendo.

    Por que el apagado ordenado va ACA y no en un handler de senal propio:
    uvicorn ya atrapa SIGTERM y SIGINT, y al recibirlos deja de aceptar
    conexiones, espera a los pedidos en vuelo y recien entonces corre esta
    parte de abajo del yield. Instalar nuestro propio handler con
    loop.add_signal_handler() SOBREESCRIBIRIA el de uvicorn y el servidor
    no se apagaria nunca. Como beneficio extra, asi funciona igual en
    Windows, donde add_signal_handler no existe (nota 4.1 de la consigna).
    """
    gestor.arrancar()
    yield
    await gestor.apagar()


app = FastAPI(title='Plataforma de tareas distribuidas', lifespan=ciclo)


@app.post('/tareas', status_code=201)
async def crear(pedido: modelos.TareaNueva):
    """Encola una tarea y devuelve su id. Responde sin esperar a que corra.

    async def y no def: tocamos la asyncio.Queue, que vive en el event loop
    (clase 19). Y no hace nada bloqueante: encola y vuelve.
    """
    if not gestor.aceptando:
        raise HTTPException(503, 'el servidor se esta apagando')
    try:
        ficha = gestor.encolar(pedido)
    except asyncio.QueueFull:
        raise HTTPException(503, 'la cola esta llena, intenta de nuevo')
    return {'id': ficha['id'], 'estado': ficha['estado']}


@app.get('/tareas')
async def listar(estado: str | None = None):
    """Lista las tareas, con filtro opcional por estado."""
    if estado is not None and estado not in modelos.ESTADOS:
        raise HTTPException(422, f'estado invalido: {estado}. '
                                 f'Validos: {", ".join(modelos.ESTADOS)}')
    fichas = gestor.listar(estado)
    return {'total': len(fichas), 'tareas': fichas}


@app.get('/estadisticas')
async def estadisticas():
    """Totales por estado, tiempos promedio y workers ocupados.

    Va ANTES de /tareas/{tid} a proposito: FastAPI prueba las rutas en
    orden, y si /tareas/{tid} estuviera primero no importaria porque el
    prefijo es distinto, pero conviene tener las rutas fijas arriba de las
    que tienen parametro.
    """
    return gestor.estadisticas()


@app.get('/tareas/{tid}')
async def ver(tid: str):
    """Estado y resultado de una tarea."""
    ficha = gestor.obtener(tid)
    if ficha is None:
        raise HTTPException(404, f'no existe la tarea {tid}')
    return ficha


@app.delete('/tareas/{tid}')
async def cancelar(tid: str):
    """Cancela una tarea encolada o en ejecucion.

    409 y no 404 si ya termino: el id existe, lo que no se puede es
    cancelar algo que ya paso.
    """
    ficha = gestor.obtener(tid)
    if ficha is None:
        raise HTTPException(404, f'no existe la tarea {tid}')
    if ficha['estado'] in modelos.FINALES:
        raise HTTPException(409, f'la tarea {tid} ya esta {ficha["estado"]}')

    desde = gestor.cancelar(tid)
    return {'id': tid, 'estado': ficha['estado'], 'se_cancelo_desde': desde}


if __name__ == '__main__':
    # La guarda es obligatoria: el ProcessPoolExecutor que entra en E2 usa
    # spawn en Windows y macOS, que RE-IMPORTA este modulo en cada proceso
    # hijo. Sin la guarda, cada hijo volveria a arrancar el servidor
    # (nota 4.1 de la consigna).
    import uvicorn
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000)
