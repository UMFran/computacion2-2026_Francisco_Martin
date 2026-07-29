FROM python:3.11-slim

# procps trae `ps` para poder validar el monitor contra `ps -eLf` (Día 1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends procps \
    && rm -rf /var/lib/apt/lists/*

# Sin buffering de stdout: en un contenedor querés ver los prints en tiempo real,
# no cuando se llena el buffer de bloque.
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.json .
COPY src/ ./src/

CMD ["python", "src/main.py"]
