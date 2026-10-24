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
    """
    gestor.arrancar()
    yield
    await gestor.detener()


app = FastAPI(title='Plataforma de tareas distribuidas', lifespan=ciclo)


@app.post('/tareas', status_code=201)
async def crear(pedido: modelos.TareaNueva):
    """Encola una tarea y devuelve su id. Responde sin esperar a que corra.

    async def y no def: tocamos la asyncio.Queue, que vive en el event loop
    (clase 19). Y no hace nada bloqueante: encola y vuelve.
    """
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


@app.get('/tareas/{tid}')
async def ver(tid: str):
    """Estado y resultado de una tarea."""
    ficha = gestor.obtener(tid)
    if ficha is None:
        raise HTTPException(404, f'no existe la tarea {tid}')
    return ficha


if __name__ == '__main__':
    # La guarda es obligatoria: el ProcessPoolExecutor que entra en E2 usa
    # spawn en Windows y macOS, que RE-IMPORTA este modulo en cada proceso
    # hijo. Sin la guarda, cada hijo volveria a arrancar el servidor
    # (nota 4.1 de la consigna).
    import uvicorn
    uvicorn.run('app.main:app', host='0.0.0.0', port=8000)
