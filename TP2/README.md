# TP2 — Plataforma de Tareas Distribuidas

**Computación II — Universidad de Mendoza — 2026**
Francisco Martín

Un servicio HTTP al que se le encargan trabajos, que los ejecuta de forma concurrente
con un pool de corrutinas, y que permite consultar su estado y su resultado.

> **Estado de este informe:** documento en construcción. Las secciones marcadas con ⏳
> corresponden a etapas todavía no implementadas y se completan antes de la entrega.
> Ver [PLAN.md](PLAN.md) para el cronograma.

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

Con Docker (⏳ E4):

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

**Cancelar una tarea** (⏳ E3):

```bash
curl -X DELETE localhost:8000/tareas/fe926941
```

### La API

| Método | Ruta | Qué hace | Estado |
|--------|------|----------|--------|
| `POST` | `/tareas` | Encola una tarea. Devuelve `id` y estado inicial | ✅ |
| `GET` | `/tareas` | Lista las tareas, con filtro opcional `?estado=` | ✅ |
| `GET` | `/tareas/{id}` | Estado y resultado de una tarea | ✅ |
| `DELETE` | `/tareas/{id}` | Cancela una tarea encolada o en ejecución | ⏳ E3 |
| `GET` | `/estadisticas` | Totales por estado, tiempos promedio, workers ocupados | ⏳ E3 |

Códigos de estado que devuelve:

| Código | Cuándo |
|--------|--------|
| `201 Created` | El `POST` encoló bien |
| `200 OK` | Los `GET` y el `DELETE` que cancela |
| `404 Not Found` | El `id` no existe |
| `409 Conflict` | `DELETE` de una tarea que ya terminó (⏳ E3) |
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
│   ├── tareas.py        155 líneas
│   ├── gestor.py        157 líneas
│   └── main.py           79 líneas
├── mediciones/           ⏳ E5
├── Dockerfile            ⏳ E4
├── docker-compose.yml    ⏳ E4
├── requirements.txt
├── README.md             ← este informe
├── PLAN.md               plan de ejecución por etapas
├── conceptos_TP2.html    material de estudio: los conceptos y en qué clase leerlos
├── prompt_tutor_TP2.md   el prompt de tutor de la cátedra, adaptado a este TP
└── dudas.md              ⏳
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
| `obtener(tid)` / `listar(estado)` | Lectura del registro para los `GET` |

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

⏳ **E3.** El diseño previsto:

`cancel()` no mata nada: le pide al loop que, la próxima vez que esa corrutina esté en un
`await`, en vez del resultado le **lance** `CancelledError` desde ese punto. De ahí salen
dos caminos distintos para el `DELETE`:

- **Tarea `pendiente`** (todavía en la cola): no hay Task que cancelar. Se la marca
  `cancelada` en el registro, y cuando un worker la saque la descarta sin ejecutarla. Eso ya
  está implementado en `ejecutar_una()`: el chequeo del estado al principio.
- **Tarea `ejecutando`**: hay que haber guardado el `asyncio.Task` *de la tarea* para poder
  cancelarlo. Cancelar el Task del worker mataría al worker, no a la tarea.

Sobre los recursos: el `AsyncClient` de `descargar` se crea con `async with`, así que el
`CancelledError` propaga por el `__aexit__` y **las conexiones abiertas se cierran solas**.
Esa es la razón de haberlo puesto adentro de la tarea en vez de compartirlo. El
`task_done()` de la cola va en un `finally`, porque si se saltea el `join()` del apagado
espera para siempre.

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

### Medición 1 — Concurrencia de I/O

⏳ **E5** (20 descargas secuenciales vs 20 concurrentes, con el speedup).

Evidencia preliminar de E2: una tarea `descargar` con 7 URLs, cinco de ellas con un segundo
de retardo forzado:

```
estado: completada   duración de la tarea: 1.95s

https://httpbin.org/delay/1        200    354 B   1.724s
https://httpbin.org/delay/1        200    354 B   1.639s
https://httpbin.org/delay/1        200    354 B   1.637s
https://httpbin.org/delay/1        200    354 B   1.676s
https://httpbin.org/delay/1        200    354 B   1.635s
https://example.com                200    577 B   0.151s
https://no-existe-esto-12345.com   ConnectError: getaddrinfo
```

**1,95 s contra ~8,5 s** que habría tardado secuencialmente (la suma de los tiempos
individuales). El total tiende al de la más lenta, no a la suma. La URL inexistente devolvió
su error sin tirar abajo a las otras seis: eso es `return_exceptions=True` en el `gather`.

### Medición 2 — El event loop bloqueado

⏳ **E5** (comparar la latencia de un `GET /tareas` durante un `hashear` pesado, sin
executor y con executor).

Evidencia preliminar de E2, con executor: cuatro tareas `hashear` de 10.000.000 de
iteraciones cada una, con 2 workers y 2 procesos:

```
id          arranco  termino    calculo
73fe2fe4       0.0s     4.5s       4.5s
42a847fc       0.0s     4.7s       4.7s
267480dd       4.5s     9.1s       4.5s
93013679       4.7s     9.2s       4.5s

total de pared:            9.2s
suma de los 4 cálculos:   18.3s
API durante todo eso:      peor latencia 3.0 ms
```

Dos lecturas:

- **18,3 s de CPU hechos en 9,2 s de pared.** Los dos procesos paralelizan de verdad: cada
  tarea tardó 4,5 s *esté sola o acompañada*. Con `ThreadPoolExecutor` la segunda habría
  tardado el doble, porque los threads se turnan el GIL.
- **La API respondió en 3 ms** mientras dos núcleos estaban al 100%. Ese es el número que
  resume el TP.

Falta la mitad que importa: la misma medición **sin** executor, llamando a
`hashear_bloqueante()` directamente desde la corrutina. Ahí el `GET` debería tardar lo que
falte para que termine el cálculo.

### Medición 3 — El techo del pool

⏳ **E5.** Los candidatos a ser el cuello de botella, para saber qué mirar:

- la cantidad de workers (crece la espera en cola, no el tiempo de ejecución);
- el `maxsize` de la cola (no degrada: rechaza con `503`);
- los descriptores de archivo, con muchas descargas concurrentes (aparece como excepciones);
- el `max_workers` del pool de procesos, y los núcleos de la máquina;
- la memoria del `registro`, que nunca se libera.

---

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
| La guarda `if __name__ == '__main__'` | `fork` vs `spawn` | 8 |

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

1. **Una tarea `hashear` que ya arrancó no se puede cancelar.** La cancelación se entrega en
   un `await`, y el cálculo corre en un proceso hijo sin ningún punto de suspensión. El
   `DELETE` la va a marcar `cancelada` y el worker se desentiende, pero el proceso sigue
   quemando CPU hasta terminar. Lo mismo vale para el timeout.
2. **El `registro` crece para siempre.** Cada tarea queda guardada en memoria con su
   resultado y nunca se libera. 10.000 tareas `descargar` con sus respuestas es memoria que
   no vuelve. Faltaría una política de expiración.
3. **El estado no sobrevive al reinicio.** Es lo que pide la consigna (sin base de datos),
   pero el volcado a JSON del apagado es solo para inspección: al arrancar se reporta por
   log y no se recarga.
4. **Un solo proceso de uvicorn.** Con varios workers de uvicorn cada uno tendría su propia
   cola y su propio registro en memoria, y un `GET` podría caer en el proceso que no tiene
   esa tarea. Escalar horizontalmente requeriría estado compartido.
5. **El semáforo de descargas es por tarea, no global.** Diez tareas `descargar`
   simultáneas pueden tener hasta 100 conexiones abiertas entre todas.
6. ⏳ Completar con lo que aparezca en E3–E5.

---

## 7. Lo que aprendí

⏳ **Para escribir al final** (2-3 párrafos personales). Temas sobre los que vale la pena
volver cuando esté todo andando:

- Qué cambió en mi forma de pensar la concurrencia entre el TP1 (procesos, memoria
  compartida, locks) y este (un solo hilo, corrutinas, sin locks).
- El momento en que entendí que `await` no es "esperar" sino "acá puedo ceder el control", y
  qué cosas dejaron de parecer mágicas después de eso.
- Qué me sorprendió de las mediciones: qué número esperaba y qué número salió.

---

## 8. Dudas

Ver [dudas.md](dudas.md) ⏳.

---

*Trabajo Práctico Nº 2 — Computación II — Universidad de Mendoza — 2026*
