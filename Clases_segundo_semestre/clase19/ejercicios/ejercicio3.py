#!/usr/bin/env python3
"""Ejercicio 3 (OBLIGATORIO): una API con FastAPI.

Extiende mi_api.py con lo que piden los puntos 8, 9 y 10:
  - PATCH /tareas/{id}   con un modelo de campos opcionales
  - GET /estadisticas    cantidad de tareas por estado
  - POST /tareas         rechaza si ya hay 10 pendientes

    python3 ejercicio3.py
    http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI()

TIPOS = {'esperar', 'calcular', 'leer'}
ESTADOS = {'pendiente', 'corriendo', 'terminada'}
MAX_PENDIENTES = 10

tareas: dict[int, dict] = {}
proximo_id = 1


class TareaNueva(BaseModel):
    tipo: str = Field(min_length=1)
    prioridad: int = Field(default=1, ge=1, le=5)


class TareaParche(BaseModel):
    """Todos los campos opcionales: un PATCH cambia solo lo que viene."""
    estado: str | None = None


@app.post('/tareas', status_code=201)
def crear(tarea: TareaNueva):
    global proximo_id

    if tarea.tipo not in TIPOS:
        raise HTTPException(422, f'tipo invalido: {tarea.tipo}')

    pendientes = sum(1 for t in tareas.values() if t['estado'] == 'pendiente')
    if pendientes >= MAX_PENDIENTES:
        # 429 Too Many Requests: el pedido es valido, pero el servidor no
        # lo acepta AHORA por un limite de capacidad. Reintentar mas tarde
        # puede funcionar, que es justo lo que 429 comunica.
        raise HTTPException(429, f'ya hay {pendientes} tareas pendientes')

    nueva = {'id': proximo_id, 'tipo': tarea.tipo,
             'prioridad': tarea.prioridad, 'estado': 'pendiente'}
    tareas[proximo_id] = nueva
    proximo_id += 1
    return nueva


@app.get('/tareas')
def listar():
    return list(tareas.values())


@app.get('/tareas/{id}')
def obtener(id: int):
    if id not in tareas:
        raise HTTPException(404, f'no existe la tarea {id}')
    return tareas[id]


@app.patch('/tareas/{id}')
def modificar(id: int, parche: TareaParche):
    """Punto 8: cambia solo el estado."""
    if id not in tareas:
        raise HTTPException(404, f'no existe la tarea {id}')
    if parche.estado is not None:
        if parche.estado not in ESTADOS:
            raise HTTPException(422, f'estado invalido: {parche.estado}')
        tareas[id]['estado'] = parche.estado
    return tareas[id]


@app.get('/estadisticas')
def estadisticas():
    """Punto 9: cantidad de tareas por estado."""
    conteo = {estado: 0 for estado in ESTADOS}
    for t in tareas.values():
        conteo[t['estado']] += 1
    return {'total': len(tareas), 'por_estado': conteo}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
