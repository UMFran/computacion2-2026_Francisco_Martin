#!/usr/bin/env python3
"""Lo que entra por la API y la forma de la ficha de una tarea.

Dos cosas distintas que conviene no mezclar:
  - TareaNueva: lo que manda el cliente. La valida Pydantic (clase 19).
  - la ficha:   lo que guardamos nosotros. Es un dict porque al apagar hay
                que volcarla a JSON (requisito 4 de la consigna).
"""
import time
from typing import Literal

from pydantic import BaseModel, Field

# Los cinco estados que pide la consigna. Como constantes y no strings
# sueltos para que un typo sea un NameError y no un bug silencioso.
PENDIENTE = 'pendiente'
EJECUTANDO = 'ejecutando'
COMPLETADA = 'completada'
FALLIDA = 'fallida'
CANCELADA = 'cancelada'

ESTADOS = (PENDIENTE, EJECUTANDO, COMPLETADA, FALLIDA, CANCELADA)

# Un estado es final si la tarea ya no va a cambiar mas.
FINALES = (COMPLETADA, FALLIDA, CANCELADA)


class TareaNueva(BaseModel):
    """El cuerpo del POST /tareas.

    Literal hace que un tipo invalido lo rechace Pydantic con un 422 y el
    detalle de que estaba mal, sin que escribamos una linea de validacion.
    """
    tipo: Literal['descargar', 'hashear', 'esperar']
    parametros: dict = Field(default_factory=dict)
    timeout: float = Field(default=30.0, gt=0)


def crear_ficha(tid, pedido):
    """La ficha de una tarea recien encolada.

    Los tres tiempos (encolada / inicio / fin) son lo que despues alimenta
    GET /estadisticas: la espera en cola es inicio - encolada, y la
    ejecucion es fin - inicio.
    """
    return {
        'id': tid,
        'tipo': pedido.tipo,
        'parametros': pedido.parametros,
        'timeout': pedido.timeout,
        'estado': PENDIENTE,
        'resultado': None,
        'motivo': None,
        'encolada': time.time(),
        'inicio': None,
        'fin': None,
    }
