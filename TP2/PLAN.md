# Plan de ejecución — TP2: Plataforma de Tareas Distribuidas

**Hoy:** 20/10/2026 · **Entrega:** 03/11/2026 (clase 24) · **Quedan 14 días**

---

## Punto de partida: la cátedra ya nos dio el esqueleto

Antes de escribir una línea, esto es lo más importante del plan. Tres archivos del
repo son casi el TP2 hecho a escala de juguete:

| Archivo | Qué nos da |
|---------|-----------|
| `Clases_segundo_semestre/clase21/cola.py` | **La arquitectura entera**: `asyncio.Queue` + N workers + `task_done()` en `finally` + apagado por centinela y por cancelación. Su docstring dice literalmente "la arquitectura del TP2". |
| `Clases_segundo_semestre/clase21/executor.py` | **La medición 2 ya resuelta**: el "medidor de atraso del loop" que compara sin executor / con `ProcessPoolExecutor` / con `to_thread`. Su docstring dice "Es la medición que el TP2 pide hacer". |
| `Clases_segundo_semestre/clase20/descargas.py` | **La medición 1 y la tarea `descargar`**: secuencial vs `gather` vs semáforo vs timeout, y el snippet de `httpx.AsyncClient` comentado al final. |

Y `clase21/contenido.md`, sección *"Juntando todo: la arquitectura del TP2"*, tiene
el esqueleto del `lifespan` de FastAPI con la cola, el pool y los workers.

**Consecuencia para el plan:** no inventamos arquitectura. Adaptamos esos tres
archivos, les agregamos el estado de las tareas y la capa HTTP, y el código queda
en el mismo registro que el resto de la materia (que es exactamente lo que
conviene para la defensa oral).

---

## Estructura de archivos que vamos a construir

```
TP2/
├── app/
│   ├── modelos.py        # Pydantic + el estado de una tarea (los 5 estados)
│   ├── tareas.py         # las 3 funciones: descargar, hashear, esperar
│   ├── gestor.py         # la cola, el registro de tareas, los workers, el apagado
│   └── main.py           # FastAPI: los 5 endpoints + lifespan
├── mediciones/
│   ├── medicion1_io.py       # 20 descargas secuenciales vs concurrentes
│   ├── medicion2_bloqueo.py  # atraso del event loop sin/con executor
│   └── medicion3_techo.py    # dónde se degradan los tiempos
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md             # ← el informe: 20% de la nota
├── dudas.md
├── conceptos_TP2.html    # material de estudio (no entregable, para el final)
└── prompt_tutor_TP2.md   # el prompt tutor adaptado al TP2
```

Cuatro módulos en `app/`, no más. Cada uno con una responsabilidad que se explica
en una frase — porque en la corrección hay que poder decir "esto está acá porque...".

---

## Etapas

### E1 — Esqueleto que arranca y encola de verdad · hoy (20/10)

El objetivo no es la API con datos falsos que sugiere el cronograma de la consigna:
con `cola.py` como base llegamos directo a la cola y los workers funcionando.

- [ ] `requirements.txt` + estructura de carpetas
- [ ] `modelos.py`: `TareaNueva` (Pydantic), `Estado`, el dict de una tarea
- [ ] `gestor.py`: `asyncio.Queue(maxsize=...)`, registro `dict[id] -> tarea`, el
      bucle `worker()`, arranque y parada del pool
- [ ] `main.py`: `lifespan`, `POST /tareas`, `GET /tareas`, `GET /tareas/{id}`
- [ ] `tareas.py`: solo `esperar` (es la más simple y ya permite ver estados en vivo)
- [ ] Probar con `curl`: encolar 5 `esperar` de 3s con 2 workers y ver cómo pasan
      de `pendiente` → `ejecutando` → `completada`

**Conceptos que frenamos a explicar acá:** `asyncio.Queue` vs `queue.Queue` ·
`task_done()`/`join()` · `create_task` y por qué el worker es un bucle infinito ·
por qué el `POST` devuelve al instante · `lifespan` y `app.state` · por qué no
hace falta `Lock`.

---

### E2 — Las otras dos tareas · 21/10

- [ ] `descargar`: un único `httpx.AsyncClient` + `asyncio.gather` + semáforo
- [ ] `hashear`: SHA-256 iterado N veces, fuera del loop con executor
- [ ] Decidir y justificar: `ThreadPoolExecutor` o `ProcessPoolExecutor`
- [ ] Decidir y justificar: `httpx` async o `aiohttp`

**Conceptos:** I/O-bound vs CPU-bound · `gather` vs `for` con `await` adentro ·
por qué el cliente HTTP se crea **una** vez (keep-alive, clase 19) · el GIL ·
`run_in_executor` vs `to_thread` · el costo del pickle y `fork` vs `spawn`.

---

### E3 — Cancelación, timeouts, DELETE y estadísticas · 22/10

Es el 30% de la nota (ítem "Asincronismo"). La parte más preguntable del TP.

- [ ] Guardar el `asyncio.Task` de cada tarea **en ejecución** para poder cancelarla
- [ ] `DELETE /tareas/{id}`: cancela encolada *y* en ejecución
- [ ] Timeout por tarea con `asyncio.timeout` → estado `fallida` con motivo
- [ ] `finally` que libere lo que quedó a medias (conexión HTTP, por ejemplo)
- [ ] `GET /estadisticas`: totales por estado, tiempos promedio, workers ocupados
- [ ] Qué pasa si un worker lanza una excepción no capturada (el bug silencioso de
      la clase 22) y cómo lo evitamos

**Conceptos:** `cancel()` inyecta `CancelledError` en el próximo `await` · por qué
hay que **relanzarla** · `finally` para limpieza · `asyncio.timeout` vs `wait_for` ·
`shield` · corrutinas huérfanas.

---

### E4 — Apagado ordenado + Docker · 23/10

- [ ] `SIGTERM`/`SIGINT`: dejar de aceptar tareas nuevas, esperar con límite a las
      que están en curso, volcar `estado_<timestamp>.json`
- [ ] Al arrancar, reportar por log si hay un volcado previo
- [ ] `Dockerfile` + `docker-compose.yml`, todo con `docker compose up --build`
- [ ] Verificar que `docker compose stop` (que manda SIGTERM) dispara el volcado

**Ojo con Windows:** `loop.add_signal_handler()` no existe en Windows (lo dice la
consigna en 4.1). El desarrollo rápido lo hacemos con `uvicorn` local, pero el
apagado ordenado se prueba **dentro del contenedor**. También hay que poner la
guarda `if __name__ == '__main__':` por el `spawn` del `ProcessPoolExecutor`.

**Conceptos:** catálogo de señales · async-signal-safe · centinela vs cancelación
para apagar workers · por qué el apagado tiene un límite de espera.

---

### E5 — Las tres mediciones · 25–27/10

15% de la nota, y son las que piden **números propios**.

- [ ] **Medición 1 (I/O):** 20 descargas secuenciales vs concurrentes + speedup.
      Base: `clase20/descargas.py`
- [ ] **Medición 2 (loop bloqueado):** cuánto tarda un `GET /tareas` mientras corre
      un `hashear` pesado, sin executor y con executor.
      Base: `clase21/executor.py` (el medidor de atraso)
- [ ] **Medición 3 (techo del pool):** subir tareas concurrentes hasta que los
      tiempos se degraden, y explicar **por qué** ahí (¿descriptores? ¿`maxsize`?
      ¿cantidad de workers? ¿el GIL en el executor?)
- [ ] Guardar las salidas crudas para pegarlas en el README

---

### E6 — README (el informe) + dudas.md · 28/10 – 01/11

20% de la nota. Las 7 secciones que pide la consigna:

1. Descripción y uso con ejemplos de `curl`
2. Diagrama de arquitectura (componentes + flujo de una tarea)
3. Decisiones de diseño argumentadas — las 4 preguntas de la consigna
4. Las tres mediciones con números e interpretación
5. Conceptos del curso aplicados, **citando clase por clase**
6. Limitaciones conocidas
7. Lo que aprendiste (2-3 párrafos)

El `conceptos_TP2.html` que armamos hoy es la materia prima de la sección 5.

---

### E7 — Bonus y repaso oral · 02–03/11

Solo si lo obligatorio está sólido. Por costo/beneficio, en este orden:

1. **Tests con `pytest-asyncio`** (+2%) — especialmente de cancelación. Es el que
   más impresiona y el que más te prepara para "¿qué pasa si cancelo a mitad de
   descarga?"
2. **WebSocket `/eventos`** (+2%) — se apoya en lo que ya tenemos
3. **Prioridades** (+2%) — `asyncio.PriorityQueue` + explicar la inanición

Y el repaso: las 6 preguntas de "Lo que vamos a preguntar al corregir" respondidas
en voz alta, mirando el propio código.

---

## Cómo vamos a trabajar (el acuerdo de ritmo)

- **Escribo yo la mayor parte del código**, en el registro de los ejemplos de la
  cátedra: módulos chicos, docstring en español, nombres en español, sin
  abstracciones que no se puedan defender.
- **Cada concepto se explica en el momento en que aparece en el código**, no antes
  ni después, con el puntero a la clase donde leerlo completo.
- **Freno socrático** (te pregunto antes de explicar) solo en los cinco clusters
  que seguro aparecen en la corrección:
  1. Dónde podría bloquearse el event loop
  2. Cancelación a mitad de una operación
  3. Por qué el pool de workers no necesita `Lock`
  4. `gather` vs `for` con `await`
  5. `time.sleep()` vs `asyncio.sleep()` en una corrutina
- En lo mecánico (Docker, formateo, boilerplate de Pydantic, parseo) voy directo.

---

## Riesgos

| Riesgo | Mitigación |
|--------|-----------|
| Windows: señales y `spawn` se comportan distinto | Probar apagado ordenado solo en Docker; guarda `__main__` desde el día 1 |
| Las mediciones dan números raros y no hay tiempo de rehacerlas | E5 arranca el 25, quedan 7 días de colchón |
| El README se deja para el final y sale flojo (20% de la nota) | Ir anotando decisiones **mientras** codeamos, en `dudas.md` y en los docstrings |
| Meterse con bonus antes de cerrar lo obligatorio | E7 es lo último, y solo si E1–E6 están cerradas |
