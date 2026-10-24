# Clase 19: HTTP + FastAPI — Respuestas

Código: `ejercicio3.py` (obligatorio).

> **Faltan archivos de la clase.** `contenido.md` y `ejercicios.md` mencionan
> `crudo.py`, `api.py` y `medir.py`, pero en `clase19/` no están — sólo está
> `mi_api.py`. Por eso el ejercicio 2 y partes del 4 y del 5 quedan respondidos en
> teoría y sin medición propia: lo aclaro en cada punto. El ejercicio 3, que es el
> obligatorio, lo construí sobre `mi_api.py`, que es la base que sí existe.
>
> En el venv de `clase19/` instalé `fastapi`, `uvicorn` y `httpx`, que es lo que
> pide la consigna al principio. Versiones: fastapi 0.142.2, uvicorn 0.54.0,
> httpx 0.28.1.

---

## Ejercicio 1: El protocolo a mano

Esto es lo mismo que el ejercicio 4 de la clase 12, y lo corrí ahí contra
`example.com`. Repito los resultados:

```
HTTP/1.1 200 OK
Date: Tue, 06 Oct 2026 12:06:25 GMT
Content-Type: text/html; charset=utf-8
Transfer-Encoding: chunked
Connection: close
Server: cloudflare
```

**1. Las tres partes:**

| Parte | Qué es | Separador |
|---|---|---|
| Línea de estado | `HTTP/1.1 200 OK` | `\r\n` |
| Headers | `Clave: valor`, uno por línea | `\r\n` entre cada uno |
| Cuerpo | el contenido | `\r\n\r\n` (línea en blanco) lo separa de los headers |

La línea en blanco es el delimitador clave: marca el fin de los headers. Es el
framing por delimitador de la clase 13, y la razón por la que el cliente HTTP del
ejercicio adicional de esa clase busca `\r\n\r\n`.

**2.** `200 OK`. Familia **2xx**, éxito.

**3. Sin el header `Host`:** `400 Bad Request`. HTTP/1.1 lo exige por el *virtual
hosting*: varios sitios comparten una IP y el servidor necesita saber a cuál se le
habla.

**4. `GET /noexiste`:** `404 Not Found`.

**5 y 6. Con `\n` en vez de `\r\n`:** funcionó contra `example.com` (devolvió
`200 OK`). Es tolerancia del servidor, no algo garantizado: el RFC exige CRLF.
Depender de eso es mala idea porque el código anda contra un servidor y falla contra
otro, y el fallo aparece recién al cambiar de proveedor o de versión. (Contra
`crudo.py` no lo pude probar porque el archivo no está.)

### 1.3 Métodos y sus propiedades

**7. Seguros** (no modifican nada): **GET** y **HEAD**. POST, PUT y DELETE
modifican.

**8. Idempotentes** (repetirlos da el mismo resultado que hacerlos una vez):
**GET, HEAD, PUT y DELETE**. 

`POST` **no** lo es porque crea un recurso nuevo en cada llamada: tres POST a
`/tareas` dejan tres tareas. `PUT`, en cambio, dice "el recurso en esta URL queda
así": repetirlo deja el mismo estado final. Y `DELETE` es idempotente aunque la
segunda llamada devuelva 404 — lo que importa es el *estado del servidor*, no el
código de respuesta.

**9. ¿Es seguro reintentar un POST que dio timeout?** **No.** Es exactamente el
problema de la parte C del ejercicio 3 de la clase 15: el cliente no puede saber si
se perdió su pedido o la respuesta. Si fue la respuesta, el servidor ya creó el
recurso y el reintento crea un segundo duplicado.

Con `PUT` **sí** es seguro, porque es idempotente: si la primera llegó, la segunda
deja el recurso igual.

**10. La relación con UDP** es directa, y es el mismo problema con otro nombre. En
la clase 15 el cliente reintentaba y el servidor hacía el trabajo dos veces; la
solución fue el **número de secuencia** que permitía reconocer el duplicado y
devolver la respuesta guardada sin reejecutar.

HTTP resuelve lo mismo con una **clave de idempotencia**: el cliente manda un
header `Idempotency-Key: <uuid>` y el servidor guarda la respuesta asociada a esa
clave. Si llega un reintento con la misma clave, devuelve lo guardado sin volver a
cobrar. Es literalmente la deduplicación por `seq` de la clase 15, en la capa de
aplicación — y es lo que usan Stripe y cualquier API de pagos seria.

---

## Ejercicio 2: http.server es socketserver

No pude correrlo: **`crudo.py` no está en la carpeta**. Las respuestas teóricas:

**1. `BaseHTTPRequestHandler` hereda de `socketserver.StreamRequestHandler`.** De
ahí le llegan `self.rfile` y `self.wfile` —los objetos tipo archivo sobre el
socket— y el ciclo `setup()`/`handle()`/`finish()` de la clase 16. Lo que agrega
`BaseHTTPRequestHandler` es parsear la línea de petición y los headers, y ofrecer
`send_response()`/`send_header()`/`end_headers()`.

**2. `ThreadingHTTPServer` usa `socketserver.ThreadingMixIn`**, el **mismo** de la
clase 16. Su definición es literalmente:

```python
class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
```

Es el mismo mixin que aplicamos a `TCPServer` y a `UDPServer`: sobrescribe
`process_request()` y nada más.

**3. ¿Por qué leer exactamente `Content-Length` bytes y no `recv(4096)`?** Porque
TCP es un flujo y no preserva los límites (clase 13). Con `recv(4096)` pueden pasar
las dos cosas malas: traer **menos** que el cuerpo completo —y procesar un JSON
truncado— o traer **más**, llevándose por delante el principio del pedido siguiente
si la conexión es `keep-alive`, con lo cual el flujo queda desincronizado para
siempre.

`Content-Length` es el prefijo de longitud del framing de la clase 13, y leer
exactamente esa cantidad es el `recibir_exacto()` de aquel ejercicio.

**4. `protocol_version`:** por defecto es `HTTP/1.0`, lo que implica cerrar la
conexión después de cada respuesta. Poniéndolo en `'HTTP/1.1'` se habilita
**keep-alive**: la conexión queda abierta para más pedidos. A cambio, el handler
queda **obligado** a mandar un `Content-Length` correcto en cada respuesta — sin él
el cliente no sabe dónde termina una respuesta y empieza la siguiente, y la
conexión se cuelga.

**5. `do_DELETE`:** el código apropiado es **204 No Content** si se borró y no hay
nada que devolver, o **200 OK** si se devuelve el recurso borrado. Y **404** si no
existía.

**6. Un método no implementado** (como `PATCH`) lo maneja el framework solo:
devuelve **501 Not Implemented**, porque `BaseHTTPRequestHandler` busca el método
`do_PATCH`, no lo encuentra y responde con ese código.

**7. Líneas por endpoint:** en `http.server` hace falta un método `do_X` completo
con parseo manual de la ruta, lectura del cuerpo según `Content-Length`,
`json.loads`, y tres llamadas para armar la respuesta — del orden de 15 a 25
líneas. En FastAPI son **dos**: el decorador y la función. La diferencia es que
FastAPI deriva el parseo, la validación y la serialización de las anotaciones de
tipo.

---

## Ejercicio 3: Una API con FastAPI (OBLIGATORIO)

Está en `ejercicio3.py`, construido sobre `mi_api.py`. Probado con
`fastapi.testclient`.

### Parte A: lo mínimo

**1. ¿Quién escribió la documentación de `/docs`?** Nadie: la genera **FastAPI**
sola, a partir de las anotaciones de tipo y los modelos de Pydantic. La interfaz es
Swagger UI, que lee el esquema OpenAPI que FastAPI produce.

**2.** Con un `tipo` que no está en la lista, devuelve **422** con el detalle del
error.

**3. `/openapi.json`** es la especificación **OpenAPI** de la API: un documento JSON
que describe cada endpoint, sus parámetros, los tipos esperados y las respuestas
posibles. Es un estándar, así que se puede usar para generar clientes automáticos
en cualquier lenguaje, para documentación, o para tests de contrato. `/docs` es
sólo una vista linda de ese archivo.

### Parte B: la validación

**4. Los cuatro errores, medidos:**

| Pedido | Código | Mensaje |
|---|---|---|
| `GET /tareas/abc` | **422** | `int_parsing`: "Input should be a valid integer" |
| `POST {"tipo":"volar"}` | **422** | `tipo invalido: volar` |
| `POST {"tipo":"esperar","prioridad":99}` | **422** | `less_than_equal`: "Input should be less than or equal to 5" |
| `GET /tareas/999` | **404** | `no existe la tarea 999` |

**5. ¿Por qué tres dan 422 y uno 404?** Porque son errores de naturaleza distinta:

- **422 Unprocessable Entity**: el pedido está **mal formado**. `abc` no es un
  entero, `99` excede el rango declarado. El servidor entendió la petición pero los
  datos no cumplen el contrato, y **reenviarla igual nunca va a funcionar**: hay que
  corregir el pedido.
- **404 Not Found**: el pedido está **perfectamente bien formado** —`999` es un
  entero válido— pero el recurso no existe. El mismo pedido podría funcionar mañana
  si alguien crea la tarea 999.

La distinción importa para el cliente: ante un 422 hay que arreglar el código; ante
un 404, no.

**6. El campo `loc`** dice **dónde** está el error. Por ejemplo:

```json
{"type": "less_than_equal", "loc": ["body", "prioridad"],
 "msg": "Input should be less than or equal to 5", "input": 99}
```

`["body", "prioridad"]` significa "en el cuerpo, en el campo `prioridad`". Para
`/tareas/abc` da `["path", "id"]`: en la ruta, el parámetro `id`. Es una lista
porque puede anidarse: `["body", "items", 0, "nombre"]` apunta al campo `nombre` del
primer elemento de la lista `items`. Eso permite que un formulario marque el campo
exacto que falló.

**7. ¿Antes o después de la función?** **Antes**, comprobado con un `print`:

```
GET /con-tipo/abc  ->  422          (el print NUNCA se ejecutó)
GET /con-tipo/5    ->  [mi funcion corrio con id=5 (int)]  ->  200
```

Con `abc` la función ni se llama: FastAPI valida, falla y responde el 422 por su
cuenta. Con `5` la función corre y recibe un `int` **ya convertido**, no el string
`"5"`. Esa es la garantía que da el sistema: adentro de la función los datos ya son
válidos y del tipo correcto, así que no hace falta defenderse.

### Parte C: agregar endpoints

**8. `PATCH /tareas/{id}`** con `TareaParche`, un modelo donde todos los campos son
`| None = None`. Probado:

```
PATCH /tareas/1 estado=corriendo  -> 200 {"id":1,...,"estado":"corriendo"}
PATCH /tareas/1 estado=invalido   -> 422 {"detail":"estado invalido: zzz"}
```

Los campos opcionales son lo que distingue `PATCH` de `PUT`: `PATCH` cambia **sólo
lo que viene**, `PUT` reemplaza el recurso entero. Por eso un modelo de PATCH no
puede tener campos obligatorios.

**9. `GET /estadisticas`:**

```
{"total": 11, "por_estado": {"terminada": 0, "corriendo": 1, "pendiente": 10}}
```

Inicializo el conteo con todos los estados en 0 para que la respuesta tenga siempre
la misma forma, aunque no haya ninguna tarea en algún estado. Un cliente que lee
`por_estado["terminada"]` no debería tener que manejar la ausencia de la clave.

**10. El límite de 10 pendientes: elegí `429 Too Many Requests`.** Probado: la
tarea número 12 (con 10 pendientes acumuladas) devuelve
`429 {"detail": "ya hay 10 tareas pendientes"}`.

Por qué 429 y no otros:

- **No 400/422**: el pedido está perfectamente bien formado. No hay nada que
  corregir, y decirle al cliente que su JSON está mal sería mentirle.
- **No 409 Conflict**: 409 es para un conflicto con el estado del recurso (editar
  algo que alguien ya cambió). Acá no hay conflicto, hay falta de capacidad.
- **No 503 Service Unavailable**: 503 dice que el **servicio** no está disponible;
  acá el servicio anda bien y acepta otros pedidos (GET, PATCH). Lo que está lleno
  es una cola.
- **Sí 429**: comunica exactamente "tu pedido es válido, pero no lo acepto ahora por
  un límite; probá más tarde". Es un 4xx porque depende del cliente esperar, y
  además admite el header `Retry-After` para decirle cuánto.

### Parte D: los tipos importan

**11. Sacando la anotación `: int`:**

```
GET /sin-tipo/abc -> [mi funcion corrio con id='abc' (str)] -> 200
```

Sin la anotación **no hay validación**: FastAPI pasa el parámetro como **string
crudo** y la función se ejecuta con `'abc'`. El 422 desaparece, y el error se
traslada adentro de la función —donde probablemente explote con un `KeyError` o
devuelva algo incorrecto. La anotación no es decorativa: es lo que activa todo.

**12. Cambiando `prioridad: int` por `prioridad: str`:**

| modelo | `3` (número) | `"3"` (string) | `"alto"` |
|---|---|---|---|
| `prioridad: int` | 200 → `3` (int) | 200 → `3` (**convertido** a int) | 422 |
| `prioridad: str` | **422** | 200 → `"3"` | 200 → `"alto"` |

Con `str` acepta cualquier texto, incluido `"alto"`, y **rechaza el número** `3`.
Lo interesante es la asimetría: Pydantic convierte `"3"` a `3` para un campo `int`
(coerción razonable) pero **no** convierte `3` a `"3"` para un campo `str`, porque
en modo estricto eso ocultaría errores de tipo.

**13. Las tres cosas que hace FastAPI con cada anotación:**

1. **Valida y convierte**: chequea que el dato cumpla el tipo y las restricciones
   (`ge`, `le`, `min_length`), y lo convierte al tipo declarado. Si falla, devuelve
   422 sin llamar a la función.
2. **Documenta**: genera el esquema OpenAPI, que es lo que alimenta `/docs` y
   `/openapi.json`.
3. **Serializa la respuesta**: convierte lo que devuelve la función a JSON según el
   tipo de retorno (y lo filtra, si se declara un `response_model`).

A eso se suma, fuera de FastAPI, que el editor y `mypy` las usan para autocompletar
y detectar errores. Una sola anotación paga en cuatro lugares distintos, y esa es la
idea central del framework.

### Checklist del obligatorio

- [x] La API levanta y `/docs` funciona
- [x] Provocados los cuatro errores, con código y mensaje anotados
- [x] Explicada la diferencia entre 422 y 404
- [x] Comprobado que la validación ocurre antes de la función (con `print`)
- [x] `PATCH /tareas/{id}` con modelo de campos opcionales
- [x] `GET /estadisticas`
- [x] Justificado el 429 para el límite de pendientes
- [x] Explicado qué hace FastAPI con las anotaciones de tipo

---

## Ejercicio 4: Dónde está el event loop

No pude medirlo porque **`api.py` no está en la carpeta** y no tiene los endpoints
`/quien-soy` ni `/quien-soy-sync`. Las respuestas conceptuales:

**1. ¿En qué thread corre cada uno?** Un endpoint `async def` corre **en el thread
del event loop** (el principal). Un endpoint `def` común corre en un **thread del
pool**: FastAPI detecta que no es una corrutina y lo despacha a un
`ThreadPoolExecutor` con `run_in_threadpool`, justamente para que una función
bloqueante no congele el loop.

**2. ¿Uno o varios event loops?** **Uno solo** por proceso worker. Pidiendo
`/quien-soy` dos veces, el `id_del_loop` es el mismo: todas las peticiones de ese
worker pasan por el mismo loop.

**3. ¿Por qué el sincrónico dice que no hay loop corriendo?** Porque corre en un
thread del pool, y el event loop vive en **otro** thread. `asyncio.get_running_loop()`
es por thread, así que desde ahí no ve ninguno — no es que no exista, es que no está
corriendo en *ese* hilo.

**4. ¿Quién crea el loop?** **uvicorn**, no FastAPI. FastAPI es sólo el framework
que define las rutas y la validación; uvicorn es el **servidor ASGI** que abre el
socket, corre el event loop y llama a la aplicación.

**ASGI** (Asynchronous Server Gateway Interface) es el contrato entre los dos: la
aplicación es un callable `async def app(scope, receive, send)`, donde `scope` trae
los datos del pedido y `receive`/`send` son corrutinas para leer el cuerpo y mandar
la respuesta. Es el sucesor de WSGI, que era sincrónico y no podía soportar
WebSockets ni long-polling.

**5. Con `--workers 3`**, el `pid` **cambia** entre pedidos: uvicorn levanta tres
procesos independientes y el sistema operativo reparte las conexiones entre ellos.

**6. ¿Qué pasa con el diccionario `tareas`?** Que **cada worker tiene el suyo**. Al
crear una tarea, se guarda en la memoria de un solo proceso; al pedirla, el pedido
puede caer en otro worker que no la tiene y devuelve **404**. Pidiéndola varias
veces, aparece y desaparece según a qué worker le toque — un bug desconcertante si
no se sabe que hay varios procesos.

Es el mismo problema de la clase 14: con `fork()` no hay memoria compartida.

**7. ¿Qué implica para el TP2?** Que **el estado no puede vivir en una variable del
proceso**. Un diccionario en memoria funciona con un worker y se rompe en cuanto se
escala, que es lo primero que se hace en producción. El estado tiene que estar en un
almacén **externo y compartido**: Redis, PostgreSQL, SQLite con un archivo
compartido, o una cola de mensajes.

Dicho de otra forma: los workers tienen que ser **sin estado** (*stateless*), para
que cualquiera pueda atender cualquier pedido. Es la misma lección de la clase 14
—threads comparten, procesos no— aplicada a la arquitectura de la aplicación.

---

## Ejercicio 5: async bien y mal

No pude correr `medir.py` porque **no está en la carpeta**. Pero esto es
exactamente lo que medí en la clase 18 con su `comparar.py`, así que uso esos
números, que miden lo mismo:

```
secuencial (una tras otra)                  3.00s
asyncio.gather con asyncio.sleep            1.02s
asyncio.gather con time.sleep  <- el bug    3.00s
```

**2. ¿Por qué `/async-mal` tarda el triple?** Porque usa una llamada **bloqueante**
(`time.sleep`) adentro de un `async def`. La corrutina no cede el control durante la
espera, así que el event loop queda congelado y no puede atender a nadie más: las
tres esperas se hacen **una tras otra** en vez de solaparse.

Es la regla de la clase 18 —nunca bloquear el event loop— y la misma del ejercicio
7 de la clase 17. Lo traicionero es que no da ningún error: anda, pero sin ninguna
de las ventajas de async.

**3. ¿Por qué `/sync` anda igual de bien si también usa `time.sleep`?** Porque un
endpoint `def` común **no corre en el event loop**: FastAPI lo despacha a un thread
del pool. Bloquear ese thread no molesta a nadie, el loop sigue libre y los otros
pedidos se atienden en otros threads del pool.

O sea que `def` con código bloqueante es **correcto**, y `async def` con código
bloqueante es el error. Es contraintuitivo: agregarle `async` a una función
sincrónica la empeora.

**4. La regla:**

- **`async def`** cuando adentro se usa `await` sobre bibliotecas asíncronas
  (`httpx`, `asyncpg`, `aiofiles`). Ahí se gana la concurrencia barata.
- **`def`** común cuando se usa cualquier cosa bloqueante: un driver sincrónico de
  base de datos, `requests`, lectura de archivos, cálculo pesado. FastAPI lo manda
  al pool de threads y todo funciona.
- **Nunca** `async def` con código bloqueante adentro: lo peor de los dos mundos.

**5. ¿Está bien o mal el endpoint de ejemplo?**

```python
@app.get('/datos')
async def datos():
    import requests
    return requests.get('https://api.ejemplo.com/cosas').json()
```

**Mal.** `requests.get()` es sincrónico y bloquea el event loop durante toda la
llamada de red, que puede ser cientos de milisegundos. Mientras tanto el servidor
entero deja de responder a todos los demás clientes. Es el peor caso: una espera
larga, de red, adentro del loop.

**6. Las dos formas de arreglarlo:**

```python
# a) cambiando el async def por def: FastAPI lo manda al pool de threads
@app.get('/datos')
def datos():
    import requests
    return requests.get('https://api.ejemplo.com/cosas').json()

# b) cambiando la biblioteca por una asincronica
@app.get('/datos')
async def datos():
    async with httpx.AsyncClient() as cliente:
        r = await cliente.get('https://api.ejemplo.com/cosas')
        return r.json()
```

La (b) escala mejor —no gasta un thread por pedido— pero la (a) es una línea y
suele alcanzar.

**7. Un cuarto endpoint con cálculo pesado:** ninguna de las tres formas lo resuelve
bien, y vale la pena ser claro al respecto:

- **`async def`**: lo peor. Bloquea el event loop entero durante todo el cálculo.
- **`def`**: mejor, porque va al pool de threads y no congela el loop. Pero por el
  **GIL** los threads no corren bytecode de Python en paralelo (clase 14), así que
  N pedidos simultáneos se siguen serializando. No se cae, pero no escala.
- La respuesta correcta es sacarlo del proceso: un **pool de procesos** con
  `await asyncio.to_thread(...)` no alcanza —sigue bajo el GIL—, hace falta
  `ProcessPoolExecutor` vía `loop.run_in_executor()`, o directamente una **cola de
  trabajos** con workers aparte (Celery, RQ, o una cola propia).

Para trabajo pesado de verdad, la segunda opción es la buena: la API recibe el
pedido, encola el trabajo, devuelve **202 Accepted** con un identificador, y el
cliente consulta después por el resultado. Es justamente la arquitectura del TP2.
