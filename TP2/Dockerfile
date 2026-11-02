# Python 3.12 porque asyncio.timeout() como context manager es 3.11+
FROM python:3.12-slim

WORKDIR /app

# Las dependencias primero y en su propia capa: si solo cambia el codigo,
# Docker reutiliza la capa del pip install y el build es casi instantaneo.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# La demo guiada viaja en la imagen para poder correrla con
# `docker compose exec tareas python demo.py`, sin instalar nada en el host.
# Usa httpx, que ya esta entre las dependencias.
COPY demo.py .

EXPOSE 8000

# uvicorn recibe SIGTERM directo porque es el PID 1 del contenedor (forma
# exec de CMD, sin shell en el medio). Eso es lo que dispara el apagado
# ordenado del lifespan: con la forma shell, el shell seria el PID 1 y no
# le pasaria la senal.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
