# TP2 — Plataforma de Tareas Distribuidas

**Computación II — Universidad de Mendoza — 2026**
Francisco Martín

Un servicio HTTP al que se le encargan trabajos, que los ejecuta de forma concurrente
con un pool de corrutinas, y que permite consultar su estado y su resultado.

> **Estado:** completo salvo la sección 7, que es personal. Todo lo que se describe acá
> está implementado y probado; los números de la sección 4 son de corridas propias.

---

## 1. Descripción y uso

### Qué hace

Recibe tareas por HTTP, las encola, y las ejecuta con un pool de workers de tamaño
configurable. El `POST` responde al instante con un `id`: el cliente no espera a que la
tarea termine, la consulta después.

Soporta tres tipos de tarea, elegidos porque cada uno ejercita algo distinto:

| Tarea | Naturaleza | Qué hace |
|-------|-----------|----------|
| `descargar` | I/O-bound | Baja una lista de URLs concurrentemente; devuelve código HTTP, tamaño y tiempo de cada una |
| `hashear` | CPU-bound | Aplica SHA-256 N veces sobre un texto. Con N grande bloquearía el event loop si no se sacara del hilo |
| `esperar` | I/O simulado | Duerme N segundos. Sirve para probar cancelación y timeouts de forma determinista |

Los estados posibles son `pendiente`, `ejecutando`, `completada`, `fallida` y `cancelada`.

### Cómo se levanta

Con Docker, que es la forma recomendada:

```bash
docker compose up --build
```

Sin Docker, para desarrollo:

```bash
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
./venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

La documentación interactiva que genera FastAPI queda en `http://localhost:8000/docs`.

### Cómo se prueba

**Encolar una espera y ver el estado:**

```bash
curl -X POST localhost:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"esperar","parametros":{"segundos":5}}'
# {"id":"fe926941","estado":"pendiente"}

curl localhost:8000/tareas/fe926941
```

**Descargar varias URLs concurrentemente:**

```bash
curl -X POST localhost:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"descargar","parametros":{"urls":[
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/1",
        "https://example.com"]}}'
```

**Un hash pesado, y comprobar que la API sigue respondiendo mientras calcula:**

```bash
curl -X POST localhost:8000/tareas \
  -H 'Content-Type: application/json' \
  -d '{"tipo":"hashear","parametros":{"texto":"computacion2","iteraciones":20000000}}'

# en otra terminal, mientras calcula:
curl -w '\ntiempo: %{time_total}s\n' localhost:8000/tareas
```

**Listar con filtro por estado:**

```bash
curl 'localhost:8000/tareas?estado=ejecutando'
```

**Probar el apagado ordenado** (encolar trabajo y mandar `SIGTERM`):

```bash
for i in 1 2 3 4 5; do
  curl -s -X POST localhost:8000/tareas -H 'Content-Type: application/json'     -d '{"tipo":"esperar","parametros":{"segundos":3}}'
done

docker compose stop          # manda SIGTERM
docker compose logs --tail 20
ls estados/                  # estado_<timestamp>.json
```

En el log se ve la secuencia: deja de aceptar tareas, los workers se retiran
ordenadamente, y el estado se vuelca a JSON.

**Cancelar una tarea:**

```bash
curl -X DELETE localhost:8000/tareas/fe926941
```

### La API

| Método | Ruta | Qué hace | Estado |
|--------|------|----------|--------|
| `POST` | `/tareas` | Encola una tarea. Devuelve `id` y estado inicial | ✅ |
| `GET` | `/tareas` | Lista las tareas, con filtro opcional `?estado=` | ✅ |
| `GET` | `/tareas/{id}` | Estado y resultado de una tarea | ✅ |
| `DELETE` | `/tareas/{id}` | Cancela una tarea encolada o en ejecución | ✅ |
| `GET` | `/estadisticas` | Totales por estado, tiempos promedio, workers ocupados | ✅ |

Códigos de estado que devuelve:

| Código | Cuándo |
|--------|--------|
| `201 Created` | El `POST` encoló bien |
| `200 OK` | Los `GET` y el `DELETE` que cancela |
| `404 Not Found` | El `id` no existe |
| `409 Conflict` | `DELETE` de una tarea que ya terminó |
| `422 Unprocessable Entity` | El cuerpo no valida. Lo pone Pydantic solo |
| `503 Service Unavailable` | La cola está llena |

---

## 2. Arquitectura

### El diagrama

```
   Cliente HTTP
        │
        ▼
  ┌──────────────────────────┐
  │   API (FastAPI)          │        ┌──────────────────────┐
  │   POST   /tareas         │───────>│  Cola de tareas      │
  │   GET    /tareas         │        │  asyncio.Queue       │
  │   GET    /tareas/{id}    │        │  (maxsize=100)       │
  │   DELETE /tareas/{id}    │        │  lleva solo el id    │
  │   GET    /estadisticas   │        └──────────┬───────────┘
  └──────────────────────────┘                   │
        ▲             │                          ▼
        │             │              ┌──────────────────────┐
        │             ▼              │  Pool de workers     │
        │     ┌───────────────┐      │  2 corrutinas en     │
        └─────│   registro    │<─────│  bucle infinito      │
   estado y   │  dict id→ficha│      └──────────┬───────────┘
   resultado  │  (en memoria) │                 │
              └───────────────┘      ┌──────────┴───────────┐
                                     │                      │
                            I/O-bound ▼            CPU-bound ▼
                         await directo         ProcessPoolExecutor
                         (httpx, sleep)        (2 procesos, pickle)
```

### El flujo de una tarea, paso a paso

1. Llega un `POST /tareas`. **Pydantic valida** el cuerpo; si el tipo no es uno de los
   tres, responde `422` sin que el sistema se entere.
2. `gestor.encolar()` genera un `id`, crea la **ficha** (un dict con estado, resultado y
   tres marcas de tiempo) y la guarda en el `registro`.
3. Mete **solo el `id`** en la `asyncio.Queue` con `put_nowait()`. Si la cola está llena
   lanza `QueueFull` y el endpoint responde `503`.
4. El endpoint devuelve `201` con el `id`. **Acá termina el pedido HTTP**, sin esperar nada.
5. Un worker que estaba suspendido en `await cola.get()` se despierta, saca el `id`, busca
   la ficha y la marca `ejecutando`.
6. Según el tipo: si es I/O-bound hace `await` directo; si es CPU-bound lo manda al
   `ProcessPoolExecutor` con `run_in_executor`. **En los dos casos el event loop queda
   libre.**
7. Al terminar escribe el resultado en la ficha y la marca `completada` (o `fallida` con el
   motivo). Hace `task_done()` en un `finally` y vuelve al `get()`.
8. Un `GET /tareas/{id}` lee esa misma ficha del `registro`.

### Los archivos

```
TP2/
├── app/
│   ├── __init__.py
│   ├── modelos.py        57 líneas
│   ├── tareas.py        161 líneas
│   ├── gestor.py        361 líneas
│   └── main.py          118 líneas
├── mediciones/
│   ├── comun.py          levanta/baja los servidores de prueba
│   ├── servidor_lento.py un servidor que tarda a proposito
│   ├── medicion1_io.py
│   ├── medicion2_bloqueo.py
│   └── medicion3_techo.py
├── Dockerfile
├── docker-compose.yml
├── estados/              volcados del apagado (fuera de git)
├── requirements.txt
├── README.md             ← este informe
├── PLAN.md               plan de ejecución por etapas
├── conceptos_TP2.html    material de estudio: los conceptos y en qué clase leerlos
├── prompt_tutor_TP2.md   el prompt de tutor de la cátedra, adaptado a este TP
└── dudas.md              dudas abiertas y resueltas
```

#### `app/modelos.py` — qué entra y qué se guarda

Separa dos cosas que conviene no mezclar:

- **`TareaNueva`** es el modelo Pydantic del cuerpo del `POST`. El campo `tipo` es un
  `Literal['descargar','hashear','esperar']`, así que un tipo inválido lo rechaza Pydantic
  con un `422` y el detalle del error, **sin una línea de código de validación propia**.
- **`crear_ficha()`** devuelve la ficha de una tarea: un `dict` con el estado, el resultado,
  el motivo del fallo y tres marcas de tiempo (`encolada`, `inicio`, `fin`). De esos tres
  tiempos salen las estadísticas: la espera en cola es `inicio - encolada` y la ejecución es
  `fin - inicio`.
- Los cinco estados están como **constantes de módulo** y no como strings sueltos, para que
  un typo sea un `NameError` en vez de un bug silencioso.

#### `app/tareas.py` — las funciones de trabajo

Este módulo **no sabe que existe una cola, ni un worker, ni una API**: recibe parámetros y
devuelve un resultado. Eso lo hace probable suelto desde el intérprete, y es lo que permitió
agregar dos tareas en E2 sin tocar ningún otro archivo.

| Función | Qué hace |
|---------|----------|
| `esperar(segundos)` | `await asyncio.sleep()`. Nunca `time.sleep()` |
| `_bajar(cliente, url, sem)` | Una descarga: código HTTP, bytes y tiempo. Toma un permiso del semáforo antes |
| `descargar(urls)` | Todas las URLs con `asyncio.gather`, sobre **un solo** `AsyncClient` |
| `hashear_bloqueante(texto, n)` | El cálculo puro. **Sincrónica y a nivel de módulo**, porque el `ProcessPoolExecutor` la manda al hijo por pickle y necesita importarla por nombre |
| `hashear(texto, n, pool)` | El envoltorio que la manda al pool con `run_in_executor` |
| `ejecutar(tipo, parametros, pool)` | Despacha al tipo que corresponda |

#### `app/gestor.py` — el corazón

La cola, el registro y el pool de workers. Es el mismo patrón que
`Clases_segundo_semestre/clase21/cola.py`: una `asyncio.Queue`, N corrutinas en bucle
infinito, y `task_done()` en un `finally`.

| Función | Qué hace |
|---------|----------|
| `arrancar()` | Crea la cola y el `ProcessPoolExecutor`, y lanza los workers. Lo llama el `lifespan` |
| `detener()` | Cancela los workers, los espera con `return_exceptions=True` y cierra el pool |
| `worker(wid)` | El bucle infinito: `await cola.get()` → ejecutar → `task_done()` |
| `ejecutar_una(tid)` | Ejecuta una tarea y deja el resultado en su ficha. Acá está el manejo de errores |
| `encolar(pedido)` | Crea la ficha y mete el `id` en la cola. No espera nada |
| `cancelar(tid)` | Los dos caminos del `DELETE`: marcar la ficha si está en cola, o `cancel()` del Task si está corriendo |
| `obtener(tid)` / `listar(estado)` | Lectura del registro para los `GET` |
| `estadisticas()` | Totales por estado, promedios de espera y ejecución, workers ocupados y tamaño de la cola |

#### `app/main.py` — la capa HTTP

Los endpoints **encolan y leen fichas, nada más**: no saben cómo se ejecuta una tarea. El
`lifespan` arranca y apaga el pool junto con la aplicación — es el esqueleto que da la
clase 21 en *"Juntando todo: la arquitectura del TP2"*.

---

## 3. Decisiones de diseño

### ¿Por qué `asyncio.Queue` y no `queue.Queue`?

Las dos son colas FIFO seguras para concurrencia. La diferencia está en **cómo esperan
cuando están vacías**.

`queue.Queue.get()` con la cola vacía **bloquea el hilo**. Y el hilo acá es uno solo: el
del event loop, donde viven también las corrutinas que atienden los pedidos HTTP. O sea que
el servidor quedaría congelado *justo cuando no tiene trabajo* — que es su estado normal.
No se atendería ningún `GET`, no se dispararía ningún timeout, nada avanzaría. El sistema
estaría muerto esperando.

`asyncio.Queue.get()` es una corrutina: si la cola está vacía **suspende la corrutina** y
registra que espera un item. El loop se va a atender a los demás. Cuando `encolar()` hace
`put_nowait()`, el loop despierta a uno de los workers que estaban esperando.

Es el mismo razonamiento que `time.sleep` vs `asyncio.sleep`: no se trata de velocidad, se
trata de **quién espera**.

### ¿Cómo evito que una tarea CPU-bound congele la API?

El problema es anterior al GIL: el event loop es **un solo hilo** y es **cooperativo**. No
puede interrumpir a una corrutina en el medio — solo recupera el control cuando la corrutina
llega a un `await`. Una corrutina que calcula hashes durante 5 segundos sin un solo `await`
monopoliza el hilo esos 5 segundos: ningún pedido se atiende, ningún timeout se dispara.

La solución es sacar el cálculo del hilo del loop:

```python
loop = asyncio.get_running_loop()
digest = await loop.run_in_executor(pool, hashear_bloqueante, texto, iteraciones)
```

Desde la corrutina esto se ve como cualquier otro `await`: se suspende y el loop queda
libre. El cálculo corre en otro proceso.

**Elegí `ProcessPoolExecutor` y no `ThreadPoolExecutor`**, y la razón es el GIL: en CPython
solo un thread ejecuta bytecode a la vez, así que cuatro threads calculando hashes tardarían
casi lo mismo que uno. Cada proceso tiene su propio intérprete y su propio GIL, así que hay
paralelismo real. La medición está en la sección 4.

El costo de esa elección, que es honesto declarar: los argumentos y el resultado viajan por
**pickle**, y una tarea que ya arrancó en un proceso hijo **no se puede cancelar**
(ver limitaciones).

Dos detalles de implementación que no son casuales:
- El pool se crea **una vez** en `arrancar()`, no por tarea: arrancar un proceso cuesta
  cargar un intérprete entero (clase 22, *"Crear el pool una vez"*).
- `hashear_bloqueante` es una función **sincrónica a nivel de módulo**. Una lambda o una
  función anidada no se pueden picklear.

### ¿Cómo implementé la cancelación, y qué pasa con los recursos a medio usar?

`cancel()` no mata nada: le pide al loop que, la próxima vez que esa corrutina esté en un
`await`, en vez del resultado le **lance** `CancelledError` desde ese punto. Sobre eso se
construyen los dos caminos del `DELETE`.

**El problema de diseño:** si el worker hiciera `await ejecutar_una(tid)`, el único
`asyncio.Task` existente sería el del worker — y cancelarlo mataría al worker, no a la
tarea. Por eso el worker envuelve cada tarea en un Task aparte y lo guarda en el dict
`ejecutando`:

```python
tid = await cola.get()
try:
    tarea_actual = asyncio.create_task(ejecutar_una(tid))
    ejecutando[tid] = tarea_actual
    try:
        await tarea_actual
    except asyncio.CancelledError:
        if tid not in cancelados_por_delete:
            raise                 # nos cancelaron al WORKER: nos vamos
        cancelados_por_delete.discard(tid)   # cancelaron la TAREA: seguimos
finally:
    ejecutando.pop(tid, None)
    cola.task_done()
```

**Los dos casos del `DELETE`:**

- **Tarea `pendiente`** (todavía en la cola): no hay Task que cancelar. Solo se marca la
  ficha como `cancelada`, y cuando un worker la saque la descarta sin ejecutarla — el
  chequeo está al principio de `ejecutar_una()`.
- **Tarea `ejecutando`**: se busca su Task en `ejecutando` y se le hace `cancel()`.

**Por qué hace falta el set `cancelados_por_delete`:** una cancelación de tarea y una
cancelación del worker llegan como **el mismo** `CancelledError`, y el worker tiene que
reaccionar distinto a cada una (seguir vivo en el primer caso, irse en el segundo). El set
registra qué ids pidió cancelar el `DELETE` y es lo que permite distinguirlas.

**Por qué no hay un hueco entre los dos casos:** entre que `cola.get()` devuelve el `id` y
que se guarda en `ejecutando` **no hay ningún `await`**, así que el `DELETE` no puede caer
en el medio: o encuentra la tarea en la cola, o la encuentra en `ejecutando`. Nunca en un
limbo. Es la misma propiedad por la que no hace falta un `Lock`.

**Los recursos a medio usar:**

- El `AsyncClient` de `descargar` se crea con `async with`, así que el `CancelledError`
  propaga por el `__aexit__` y **las conexiones abiertas se cierran solas**. Esa es la razón
  de haberlo puesto adentro de la tarea en vez de compartirlo en `app.state`.
- El `task_done()` va en un `finally`, porque si se saltea, el `join()` del apagado espera
  para siempre.
- El `ejecutando.pop()` también va en el `finally`: si no, `/estadisticas` reportaría para
  siempre un worker ocupado que no existe.
- `CancelledError` **se relanza siempre** en `ejecutar_una()`. Tragarla dejaría al resto del
  sistema creyendo que la tarea sigue viva.

**Y el límite del mecanismo**, que es importante poder decir antes de que lo pregunten: la
cancelación se entrega *en un `await`*. Una tarea sin `await`s por delante no se entera. Un
`hashear` que ya arrancó en un proceso hijo queda marcado `cancelada` y el worker se
desentiende, pero el proceso sigue quemando CPU hasta terminar. Está medido en la
sección 6.

### ¿Cómo implementé los timeouts?

```python
async with asyncio.timeout(ficha['timeout']):
    ficha['resultado'] = await tareas.ejecutar(...)
```

Un timeout **es una cancelación con reloj**, no un mecanismo aparte: al vencer, cancela la
corrutina de adentro con el mismo `cancel()` de antes, y convierte el `CancelledError`
resultante en `TimeoutError` para quien espera afuera. Por eso el `except TimeoutError` va
antes del `except asyncio.CancelledError`, y por eso valen las mismas limitaciones: una
tarea CPU-bound en un proceso hijo tampoco se entera del timeout.

Al vencer, la tarea pasa a `fallida` con el motivo, como pide la consigna. El timeout es
configurable por tarea (campo `timeout` del `POST`, 30 s por omisión).

### ¿Qué pasa si un worker lanza una excepción no capturada?

Sin defensa, pasa lo peor: **el worker muere en silencio**. Una excepción dentro de un Task
no se propaga sola, queda guardada esperando que alguien pida el resultado — y a los workers
nadie les pide el resultado. No habría traceback ni log. El sistema seguiría aceptando
`POST` con un consumidor menos, y con mala suerte mueren los dos y la cola crece para
siempre mientras la API responde `201` con total normalidad.

La defensa está en `ejecutar_una()`:

```python
except Exception as e:
    ficha['estado'] = modelos.FALLIDA
    ficha['motivo'] = f'{type(e).__name__}: {e}'
    log.warning('tarea %s fallo: %s', tid, ficha['motivo'])
```

`except Exception` y **no** `except BaseException`, a propósito: `CancelledError` hereda de
`BaseException` justamente para que un `except` genérico no se la trague. Así una tarea que
falla se marca `fallida` y el worker sigue vivo, pero una cancelación sigue propagando.

Verificado: una tarea con parámetros inválidos quedó `fallida` con el motivo, y el worker
siguió tomando tareas después.

### ¿Por qué la cola lleva el `id` y no la tarea entera?

Para que haya **una sola fuente de verdad**. El `registro` es el único lugar donde vive el
estado. Si la cola llevara copias de las fichas habría dos versiones del estado, y un
`DELETE` sobre una tarea todavía encolada modificaría una copia que el worker no va a mirar.

### ¿Cómo implementé el apagado ordenado?

Los cuatro pasos que pide la consigna están en `gestor.apagar()`:

1. `aceptando = False`, y el `POST` empieza a responder `503`.
2. Se mete un **centinela por worker** en la cola. Cada worker consume el suyo y se
   retira — pero recién *después* de terminar lo que tenía entre manos, así que
   **ninguna tarea queda a medias**. Es la variante que `clase21/cola.py` señala como
   "lo que el TP2 pide para SIGTERM".
3. `await asyncio.wait_for(asyncio.gather(*workers), ESPERA_APAGADO)` — la espera **con
   límite**. Si se agota, `wait_for` cancela el gather, que cancela a los workers: el
   centinela es el camino amable y la cancelación es el plan B.
4. `volcar_estado()` escribe `estados/estado_<timestamp>.json` con el registro completo.

Que la ficha sea un `dict` y no un objeto Pydantic paga justamente acá: ya es JSON, no
hay que serializar nada a mano.

Al arrancar, `reportar_volcado_previo()` busca volcados anteriores y los reporta por log
con la cantidad de tareas que contenían. **No restaura el estado** — la consigna pide
reportarlo, no recargarlo.

Un detalle de alcance que conviene aclarar: el centinela se encola *al final*, así que
los workers procesan todo lo que había antes que él. O sea que el apagado espera a toda
la cola, no solo a lo que estaba en ejecución — más generoso que lo que pide la consigna,
y acotado igual por el límite de tiempo.

### ¿Por qué el apagado está en el `lifespan` y no en un handler de señal propio?

Esta es la decisión que más se desvía de lo que sugiere el enunciado, así que vale
explicarla: **uvicorn ya atrapa `SIGTERM` y `SIGINT`**. Al recibirlos deja de aceptar
conexiones, espera a los pedidos en vuelo, y recién entonces corre la parte de abajo del
`yield` del `lifespan` — que es donde está `apagar()`.

Instalar nuestro propio handler con `loop.add_signal_handler()` **sobreescribiría el de
uvicorn**, y el servidor no se apagaría nunca: el handler es uno por señal, no una cadena.

Como beneficio extra, así funciona igual en Windows, donde `add_signal_handler()` no
existe (nota 4.1 de la consigna). El concepto de **async-signal-safe** igual aplica y es
lo que uvicorn hace internamente: el handler no hace el trabajo, solo le avisa al loop,
que lo ejecuta cuando le toca.

En el `docker-compose.yml` hay un detalle que importa: `stop_grace_period: 20s`. Docker
manda `SIGTERM` y espera —por omisión 10 s— antes de mandar `SIGKILL`, que **no se puede
atrapar**. Como `ESPERA_APAGADO` es 10 s, con el valor por omisión el `SIGKILL` llegaría
justo encima y el volcado no alcanzaría a escribirse.

Y en el `Dockerfile`, el `CMD` está en forma **exec** (lista de strings, sin shell): así
uvicorn es el PID 1 y recibe la señal directo. Con la forma shell, el shell sería el PID 1
y no se la pasaría.

### ¿Por qué `httpx` y no `aiohttp`?

La consigna prohíbe `requests` —es sincrónico, bloquearía el loop igual que `time.sleep()`—
y deja elegir entre los dos asíncronos.

Elegí `httpx` porque tiene **la misma API en modo sincrónico y asíncrono**. Eso hace que la
medición 1 (secuencial contra concurrente) sea el mismo código con una línea cambiada, en
vez de dos programas distintos — y si fueran dos programas distintos siempre quedaría la
duda de si la diferencia de tiempo viene de la concurrencia o de la librería. Además ya
venía instalado en el entorno de la clase 19, porque es lo que usa el `TestClient` de
FastAPI.

`aiohttp` es algo más rápido en benchmarks y es nativo async; la decisión es defendible en
los dos sentidos, pero el argumento de la medición pesó más.

### ¿Cómo se configura el tamaño del pool?

Por variables de entorno, con los valores por omisión en el código:

| Variable | Por omisión | Qué controla |
|---|---|---|
| `TP2_WORKERS` | 2 | Corrutinas worker que consumen de la cola |
| `TP2_PROCESOS` | 2 | Procesos del `ProcessPoolExecutor` |
| `TP2_COLA` | 100 | `maxsize` de la `asyncio.Queue` |
| `TP2_ESPERA_APAGADO` | 10 | Segundos máximos de espera en el apagado |
| `TP2_DIR_ESTADOS` | `estados` | Dónde van los volcados |

La medición 3 las usa para barrer configuraciones sin tocar el código.

### ¿Por qué `put_nowait()` y no `await put()`?

La consigna exige que el `POST` responda inmediatamente. Con la cola llena, `await put()`
dejaría al endpoint esperando que se libere lugar — y el tiempo de respuesta pasaría a
depender de la carga. `put_nowait()` lanza `QueueFull` y el endpoint responde `503`, que es
rechazar rápido y ser honesto con el cliente.

El `maxsize=100` tampoco es una optimización: es la política de qué pasa cuando entra
trabajo más rápido de lo que sale. Sin límite la cola crece hasta consumir la memoria, y el
sistema no falla rápido y claro sino que se degrada lento y muere raro.

---

## 4. Mediciones

Los tres scripts están en `mediciones/` y se corren desde `TP2/`:

```bash
python -m mediciones.medicion1_io
python -m mediciones.medicion2_bloqueo
python -m mediciones.medicion3_techo
```

Cada uno levanta por su cuenta los servidores que necesita y los baja al terminar; no hay
que arrancar nada a mano. Las mediciones 1 y 3 miden contra un servidor local
(`mediciones/servidor_lento.py`) en vez de contra sitios reales, **a propósito**: la
latencia de internet varía entre corridas y ensuciaría los números. Con un servidor local
el retardo lo elegimos nosotros, los resultados se repiten, y se pueden reproducir sin
conexión.

Todos los números son de una misma máquina (Windows 11, Python 3.13, 8 núcleos lógicos).

### Medición 1 — Concurrencia de I/O

20 descargas de 0,5 s cada una. Cota teórica: secuencial = 10,0 s (la suma),
concurrente = 0,5 s (la más lenta).

| Estrategia | Total | Cada descarga |
|---|---|---|
| **secuencial** (`for` + `await`) | **10,27 s** | 0,514 s |
| **concurrente** (`gather`) | **0,60 s** | 0,569 s |
| concurrente, semáforo de 10 | 1,08 s | 0,532 s |
| concurrente, semáforo de 5 | 2,10 s | 0,523 s |

**Speedup: 17,1x.**

Interpretación. El secuencial da la suma de las 20 esperas porque `await` significa
"esperá esto": en un bucle, espera una por una. El `gather` las lanza todas antes de
esperar, así que el total tiende al de la más lenta.

El speedup **no es 20x**, y entender por qué importa más que el número: el techo no es la
cantidad de URLs sino la relación entre la suma de las esperas y la espera más larga, y
hay costos que no desaparecen (las conexiones, el parseo de las 20 respuestas, el propio
scheduling del loop). Esos 0,10 s de overhead sobre la cota teórica son eso.

El semáforo muestra el precio de acotar: con 10 permisos hay que hacer 2 tandas (1,08 s) y
con 5 hay que hacer 4 (2,10 s). Es exactamente lo que se paga para no abrir 20 conexiones
de golpe, y es lo que usa la tarea `descargar`.

### Medición 2 — El event loop bloqueado

Una tarea `hashear` de 12.000.000 de iteraciones (≈5 s de CPU), midiendo la latencia de
`GET /tareas` desde afuera del proceso del servidor mientras corre.

| | Duración del cálculo | `GET`s atendidos | Peor `GET` | `GET` medio |
|---|---|---|---|---|
| **SIN `run_in_executor`** | 5,10 s | **1** | **4803 ms** | 4803,3 ms |
| **CON `run_in_executor`** | 4,74 s | **45** | **2 ms** | 1,4 ms |

**La API se degradó 2493x: de 2 ms a 4,8 segundos.**

Interpretación. Sin executor el `GET` no se atiende hasta que el cálculo termina. El event
loop es **un solo hilo** y la corrutina que calcula no tiene ningún `await` donde ceder el
control — no es contención, es que nunca lo devuelve. Por eso durante los 5 segundos entró
**un solo** `GET` (el que quedó encolado en el socket) en vez de 45.

Y el número que más dice: **el cálculo tardó lo mismo en los dos casos** (5,10 s contra
4,74 s). El executor no acelera nada. Lo único que cambia es que el resto del sistema sigue
vivo. Asyncio es sobre aprovechamiento, no sobre velocidad.

Lo que no se ve en la tabla pero vale aclarar: durante esos 5 segundos tampoco se habría
disparado ningún timeout, ni avanzado ningún otro worker, ni aceptado ninguna tarea nueva.
El servidor entero estaba muerto.

> **Nota de honestidad.** Para poder medir la mitad "mala" hubo que agregarle a la tarea
> `hashear` un parámetro `sin_executor` que llama al cálculo directo desde la corrutina.
> Existe **solo** para esta medición y está documentado como tal en `tareas.py`; en uso
> normal nunca se usa.

### Medición 3 — El techo del pool

La pregunta no tiene una sola respuesta: hay varios cuellos de botella y cada uno se rompe
distinto. El script los separa en cuatro escenarios.

**A) Tareas I/O-bound (`esperar` 1 s) con 2 workers**

| Tareas | Pared | Latencia media | Espera en cola | Cota teórica (N/2) |
|---|---|---|---|---|
| 2 | 1,03 s | 1,01 s | 0,00 s | 1,00 s |
| 4 | 2,02 s | 1,51 s | 0,50 s | 2,00 s |
| 8 | 4,08 s | 2,52 s | 1,51 s | 4,00 s |
| 16 | 8,10 s | 4,54 s | 3,53 s | 8,00 s |
| 32 | 16,16 s | 8,55 s | 7,55 s | 16,00 s |
| 64 | 32,31 s | 16,62 s | 15,61 s | 32,00 s |

El techo **no es la cantidad de tareas**: es `CANTIDAD_WORKERS`. Cada tarea sigue tardando
1 s; lo que crece es la **espera en cola**, lineal con tareas/workers. Y eso no es
degradación, es encolamiento — que es el comportamiento correcto. El tiempo de pared sigue
la cota teórica con menos de un 2% de error.

**B) Las mismas tareas con 8 workers**

| Tareas | Pared | Latencia media | Espera en cola |
|---|---|---|---|
| 2 | 1,06 s | 1,01 s | 0,00 s |
| 4 | 1,03 s | 1,01 s | 0,00 s |
| 8 | 1,03 s | 1,01 s | 0,00 s |
| 16 | 2,07 s | 1,51 s | 0,50 s |
| 32 | 4,05 s | 2,51 s | 1,50 s |
| 64 | 8,09 s | 4,51 s | 3,50 s |

El techo se corrió exactamente donde se esperaba: plano hasta 8 tareas, y de ahí en más
crece con N/8. El mismo trabajo sale **4x más rápido**. Subir workers es casi gratis
mientras las tareas sean I/O-bound, porque no consumen CPU mientras esperan — ese es todo
el argumento de asyncio.

**C) Tareas CPU-bound (`hashear` 4M) con 8 workers pero solo 2 procesos**

| Tareas | Pared | Latencia media | Cálculo medio |
|---|---|---|---|
| 1 | 1,86 s | 1,83 s | 1,83 s |
| 2 | 1,82 s | 1,71 s | 1,79 s |
| 4 | 3,30 s | 2,43 s | 3,28 s |
| 8 | 6,65 s | 4,04 s | 6,59 s |

Acá los workers dejan de servir. Con 1 y con 2 tareas el tiempo es el mismo (los 2 procesos
trabajan en paralelo), y de 2 en adelante se duplica cada vez que se duplica la carga. **8
workers no hacen nada si hay 2 procesos**: las tareas hacen cola en el executor en vez de
en la `asyncio.Queue`. El cuello de botella pasó de los workers a `MAX_PROCESOS` y, detrás
de eso, a los núcleos de la máquina.

**D) Ráfaga más grande que la cola** — 150 tareas de golpe contra una cola de 100:

```
aceptadas            104
rechazadas con 503    46
```

Acá **no hay degradación: hay rechazo**, y es deliberado. (104 y no 100 porque mientras se
mandaba la ráfaga los workers ya habían drenado algunas.) Con una cola infinita el sistema
no fallaría rápido y claro: se degradaría lento hasta quedarse sin memoria.

**Respuesta a "si te mando 10.000 tareas de golpe, ¿qué se rompe primero?"**

La cola. Entran 100 y se rechazan 9.900 con `503`, que es el comportamiento buscado. Si la
cola fuera infinita, el siguiente límite sería la memoria del `registro`, que guarda cada
ficha con su resultado para siempre y nunca libera nada (limitación 2). Y si las tareas
fueran `descargar` sin semáforo, antes que eso se agotarían los descriptores de archivo del
proceso.

## 5. Conceptos del curso aplicados

| Pieza del código | Concepto | Clase |
|------------------|----------|-------|
| `gestor.worker()` consumiendo de la cola | Productor-consumidor, pero con corrutinas | 11 y 21 |
| No hay ningún `Lock` | El punto de cambio de contexto es el `await` | 11 y 20 |
| `asyncio.Semaphore` en `_bajar()` | Acotar la concurrencia | 11 y 20 |
| `await cola.get()` que suspende en vez de bloquear | El event loop y las corrutinas | 18 |
| `asyncio.sleep` en `esperar()` | Bloqueante vs no bloqueante | 17 y 18 |
| `asyncio.gather` en `descargar()` | Concurrencia real vs secuencial | 18 y 20 |
| `httpx.AsyncClient` reutilizado | Keep-alive de HTTP/1.1 | 19 |
| `TareaNueva` con Pydantic | Validación declarativa, `422` automático | 19 |
| Los endpoints son `async def` | Dónde corre cada endpoint | 19 |
| El `lifespan` que crea la cola y el pool | La arquitectura del TP2 | 21 |
| `run_in_executor` en `hashear()` | Sacar el trabajo pesado del loop | 21 |
| `ProcessPoolExecutor` y no threads | El GIL | 10 y 22 |
| `hashear_bloqueante` a nivel de módulo | El pickle entre procesos | 22 |
| `except Exception` que no atrapa `CancelledError` | El bug silencioso de las excepciones en Tasks | 22 |
| `task_done()` en un `finally` | La cuenta de la cola y el `join()` | 21 |
| `tarea.cancel()` en `gestor.cancelar()` | `CancelledError` se entrega en el próximo `await` | 20 |
| `async with asyncio.timeout()` | Un timeout es una cancelación con reloj | 20 |
| El Task por tarea, aparte del worker | Corrutina vs Task: qué agrega `create_task` | 18 y 21 |
| La guarda `if __name__ == '__main__'` | `fork` vs `spawn` | 8 |
| El centinela del apagado en `apagar()` | Apagado ordenado: centinela vs cancelación | 20 y 21 |
| `SIGTERM`/`SIGINT` atrapados por uvicorn | Catálogo de señales, async-signal-safe | TP1 |
| `wait_for(gather(*workers), ...)` | Esperar con límite | 20 |

Un ejemplo desarrollado, del estilo que pide la consigna:

> El pool de workers consume de una `asyncio.Queue` compartida. Es el mismo patrón
> productor-consumidor de la clase 11, pero con corrutinas en vez de threads: acá no hace
> falta `Lock` porque el event loop no interrumpe entre `await`s. En la clase 11 el sistema
> operativo podía interrumpir un thread en cualquier instrucción de bytecode —incluso en el
> medio de un `contador += 1`, que son varias— y de ahí la race condition. Con corrutinas el
> punto de cambio es explícito y está escrito en el código: el bloque que marca una ficha
> como `ejecutando` y le pone la hora de inicio no tiene ningún `await` adentro, así que
> ninguna otra corrutina puede verlo a medio aplicar.

---

## 6. Limitaciones conocidas

1. **Una tarea `hashear` que ya arrancó no se puede cancelar**, y eso roba capacidad del
   pool. La cancelación se entrega en un `await`, y el cálculo corre en un proceso hijo sin
   ningún punto de suspensión: el `DELETE` marca la ficha `cancelada` y el worker se libera
   al instante, pero el proceso sigue calculando.

   Medido, aprovechando que el pool tiene 2 procesos: se toma como referencia el tiempo de
   dos `hashear` de 10.000.000 de iteraciones, y se repite lo mismo después de haber
   cancelado un `hashear` de 60.000.000.

   | | Pared | Cada cálculo |
   |-|-------|--------------|
   | Con los 2 procesos libres | **5,1 s** | 4,44 s · 4,96 s |
   | Después de cancelar un hash de 60M | **16,2 s** | 7,91 s · 16,07 s |

   Tres veces más lento. El cálculo cancelado siguió consumiendo un núcleo, así que los dos
   nuevos tuvieron que competir por lo que quedaba. El `DELETE` respondió en 1 ms y la ficha
   quedó `cancelada` — desde la API todo parecía correcto, y el costo estaba escondido en el
   pool.

   Mitigaciones posibles, ninguna implementada: partir el cálculo en bloques con un `await`
   entre ellos para darle puntos de cancelación; o matar el proceso hijo con
   `pool.shutdown(cancel_futures=True)` y recrear el pool, que es brutal porque se lleva
   también las otras tareas en vuelo.
2. **El `registro` crece para siempre.** Cada tarea queda guardada en memoria con su
   resultado y nunca se libera. 10.000 tareas `descargar` con sus respuestas es memoria que
   no vuelve. Faltaría una política de expiración.
3. **El estado no sobrevive al reinicio.** Es lo que pide la consigna (sin base de datos),
   pero conviene ser explícito: el volcado a JSON es solo para inspección. Al arrancar se
   reporta por log y **no se recarga**, así que las tareas que quedaron `pendiente` en el
   volcado no se reencolan: se pierden.
4. **El apagado ordenado no se puede probar en Windows sin Docker.** `add_signal_handler`
   no existe ahí y la entrega de `SIGTERM` es distinta. La lógica de `apagar()` se probó
   llamándola directamente; la ruta de la señal se verifica en el contenedor.
5. **Un solo proceso de uvicorn.** Con varios workers de uvicorn cada uno tendría su propia
   cola y su propio registro en memoria, y un `GET` podría caer en el proceso que no tiene
   esa tarea. Escalar horizontalmente requeriría estado compartido.
6. **El semáforo de descargas es por tarea, no global.** Diez tareas `descargar`
   simultáneas pueden tener hasta 100 conexiones abiertas entre todas.
7. **El `registro` no distingue entre tareas viejas y nuevas en `/estadisticas`.** Los
   promedios son sobre todas las tareas desde que arrancó el proceso, así que una ráfaga
   vieja sesga el promedio para siempre. Faltaría una ventana móvil.
8. **El parámetro `sin_executor` de `hashear` existe solo para la medición 2** y no debería
   estar en una API de producción: deja que un cliente bloquee el servidor a propósito.

---

## 7. Lo que aprendí

Lo que más me costó no fue aprender `asyncio` sino **desaprender el TP1**. Ahí los procesos
corrían de verdad al mismo tiempo, cada uno con su memoria, y para compartir algo había que
pedirle un `Manager` o un `Value` al sistema y protegerlo con un `Lock`. En este TP el
`registro` de tareas es un `dict` común, y lo tocan tres lugares distintos: el `POST` cuando
crea la ficha, el `DELETE` cuando la marca cancelada, y los workers cuando le escriben el
estado y el resultado. La primera vez que vi eso escrito quise ponerle un `Lock` por reflejo.
No hace falta, y entender *por qué* fue el salto: hay un solo hilo, así que el control nunca
cambia de manos en medio de una línea — solo cambia en un `await`. Mientras una secuencia de
asignaciones no tenga un `await` en el medio, nadie puede verla a mitad de camino.

Lo incómodo es la vuelta de eso. En el TP1 los lugares peligrosos eran visibles: estaban
donde yo había escrito el `Lock`. Acá los lugares peligrosos son **invisibles**, porque son
los `await`. Si mañana meto un `await` en el medio de esas tres líneas que escriben la ficha,
acabo de crear una condición de carrera y el código no se ve distinto. Pasé de proteger datos
a tener que mirar dónde cedo el control.

El número que no esperaba fue el de la medición 2, y no el que miré primero. Yo esperaba que
`run_in_executor` hiciera el hash **más rápido** — es lo que uno asume cuando le dicen
"mandalo a otro proceso". El cálculo tardó **5,10 s sin executor y 4,74 s con executor**:
prácticamente lo mismo. El executor no acelera nada. Lo que cambia es otra columna de la
tabla: un `GET /tareas` pasó de **4803 ms a 2 ms**, una degradación de 2493x que desaparece.
El executor no es una optimización, es un **aislamiento**: saca el trabajo del hilo del event
loop para que el resto del sistema siga respondiendo mientras ese trabajo tarda exactamente
lo mismo que antes.

El segundo que me sorprendió fue al revés, por lo mal que quedaba el sistema sin que nada
fallara: cancelar un hash de 60 millones de iteraciones devuelve `200` en un milisegundo y la
ficha queda prolijamente `cancelada`, pero el proceso hijo **sigue quemando un núcleo**. Dos
hashes nuevos pasaron de 5,1 s a 16,2 s por culpa de ese zombi. La API decía que todo estaba
bien y el sistema estaba 3x más lento. Es la limitación que más me interesa resolver y la
dejé anotada en [dudas.md](dudas.md).

---

## 8. Dudas

Ver [dudas.md](dudas.md).

---

*Trabajo Práctico Nº 2 — Computación II — Universidad de Mendoza — 2026*
