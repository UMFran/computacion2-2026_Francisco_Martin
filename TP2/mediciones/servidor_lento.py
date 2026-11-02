#!/usr/bin/env python3
"""Un servidor que tarda a proposito, para medir contra algo estable.

Por que no medir contra httpbin.org o cualquier sitio real: porque la
latencia de internet varia entre corridas y ensucia los numeros. Con un
servidor local el retardo lo elegimos nosotros, las mediciones se repiten
igual, y la catedra las puede correr sin conexion.

Lo levantan solos los scripts de medicion; no hay que arrancarlo a mano.
"""
import asyncio

from fastapi import FastAPI

app = FastAPI()


@app.get('/lento')
async def lento(s: float = 0.5, bytes: int = 1024):
    """Responde despues de s segundos, con un cuerpo de `bytes` bytes.

    asyncio.sleep y no time.sleep: si durmiera el hilo, este servidor
    atenderia de a un pedido a la vez y la medicion concurrente daria lo
    mismo que la secuencial. El bug estaria en el instrumento, no en lo
    medido.
    """
    await asyncio.sleep(s)
    return {'relleno': 'x' * bytes}
