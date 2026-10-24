#!/usr/bin/env python3
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

class TareaNueva(BaseModel):
    tipo: str = Field(min_length=1)
    prioridad: int = Field(default=1, ge=1, le=5)

@app.post('/tareas', status_code=201)
def crear(tarea: TareaNueva):            # FastAPI ve el tipo y arma el objeto
    return {'recibido': tarea.tipo, 'prioridad': tarea.prioridad}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('mi_api:app', host='127.0.0.1', port=8000, reload=True)