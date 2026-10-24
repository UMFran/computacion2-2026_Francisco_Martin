# Clase 18: De yield a asyncio — Respuestas

Código: `ejercicio1.py` (generadores), `ejercicio2.py` (scheduler, obligatorio),
`ejercicio4.py` (asyncio).

---

## Ejercicio 1: Generadores que reciben

### 1.1 send()

```
send(10) sin next() -> TypeError: can't send non-None value to a just-started generator
next(a) inicial devuelve: 0
a.send(10)  -> 10
a.send(5)   -> 15
a.send(100) -> 115
```

**1.** `TypeError: can't send non-None value to a just-started generator`. Un
generador recién creado **no ejecutó nada todavía**: está parado antes de la
primera línea, no suspendido en un `yield`. Como `send(x)` lo que hace es
"reanudar poniendo `x` como resultado del `yield` donde estaba", si no hay ningún
`yield` esperando no hay dónde dejar el valor. `send(None)` sí funciona, y es
exactamente lo que hace `next()`.

**2.** Devuelve **0**: el valor del `yield total` con `total` todavía en 0. El
`next()` inicial corre el cuerpo hasta el primer `yield` y entrega lo que haya ahí.
Esa es la razón por la que hay que "cebar" el generador antes de poder mandarle
nada.

**3.** Cada resultado es el `total` acumulado **después** de sumar lo que se mandó:
`send(10)` → el `yield` devuelve 10, se suma a 0 y la próxima vuelta entrega 10.
Después 10+5 = 15, y 15+100 = 115. El `send()` entrega un valor y recibe otro en la
misma llamada.

### 1.2 El estado sobrevive

```
voy por 0     <- c1
voy por 0     <- c2
voy por 1     <- c1
voy por 1     <- c2
voy por 2     <- c1
```

**4. ¿Comparten el `n`?** No. Cada generador tiene **su propio** `n`, y las
secuencias avanzan por separado. Dos llamadas a `contador()` crean dos objetos
generador independientes, cada uno con su marco de ejecución.

**5. ¿Dónde vive el `n` mientras está suspendido?** En el **frame** del generador,
que es un objeto de Python (`gen.gi_frame`) y vive en el heap mientras exista una
referencia al generador.

Esa es la diferencia con una función común: las variables locales de una función
viven en un frame que está en la **pila**, y se destruye al retornar. El frame de
un generador **sobrevive** entre una suspensión y la siguiente — por eso puede
retomar exactamente donde estaba, con todas sus variables intactas. Es la propiedad
sobre la que está construido todo lo demás de esta clase.

### 1.3 StopIteration lleva el resultado

```
next(t) -> 'trabajando'
StopIteration.value -> 'resultado final'
```

**6.** Imprime `resultado final`. El `return` de un generador no se obtiene como en
una función normal porque **llamar al generador no lo ejecuta**: devuelve el objeto
generador. El valor del `return` se entrega recién cuando el generador termina, y
el único canal disponible en ese momento es la excepción `StopIteration`, en su
atributo `.value`.

**7. ¿Cómo lo usó el scheduler?** Para saber que una tarea **terminó** y no
devolverla a la cola. En `scheduler()` el `try/except StopIteration` con `continue`
es justamente eso: si la tarea terminó, no vuelve a `pendientes`. Y si la tarea
devolviera un resultado, `e.value` sería la forma de recogerlo — que es
exactamente lo que hace `await` en asyncio.

---

## Ejercicio 2: Construir el scheduler (OBLIGATORIO)

### Parte A: el intercalado

```
  [A] paso 1/3      [B] paso 1/2      [C] paso 1/4
  [A] paso 2/3      [B] paso 2/2      [C] paso 2/4
  [A] paso 3/3                        [C] paso 3/4
                                      [C] paso 4/4
  reanudaciones (llamadas a next): 12
```

**1. El orden es por turnos** (round-robin): A, B, C, A, B, C, A, C, C. Cada tarea
avanza **un paso** y cede. Cuando B se queda sin pasos desaparece de la rotación, y
al final sólo queda C. Es el comportamiento de la `deque`: se saca del frente y se
devuelve al fondo.

**2. 12 reanudaciones** para 3+2+4 = 9 pasos. Los 3 de más son las llamadas que
levantan `StopIteration`: una por tarea, la que descubre que terminó. En general
son `pasos + cantidad_de_tareas`.

**3. Una tarea sin ningún `yield`:** hay que distinguir dos casos.

- Si la función **no tiene ningún `yield` en su cuerpo**, no es un generador: es
  una función común. Llamarla la ejecuta de inmediato y devuelve `None`, y el
  scheduler explota con `TypeError: 'NoneType' object is not an iterator`.
- Si tiene un `yield` **inalcanzable** (después de un `return`), sí es un generador.
  El `next()` corre el cuerpo hasta el final y lanza `StopIteration` en la primera
  reanudación. El scheduler lo trata bien: la tarea se ejecuta entera de una y sale
  de la cola. Lo medí: 4 reanudaciones para la tarea muda más una de 2 pasos.

### Parte B: la cooperación es obligatoria

```
  [A] paso 1/3
  [EGOISTA] me pongo a calcular
  [EGOISTA] listo              <- 3 segundos despues
  [B] paso 1/3
  ...
  total: 3.0s
```

**4. ¿Qué les pasa a las demás?** **Nada: no avanzan.** Entre "me pongo a calcular"
y "listo" pasan 3 segundos en los que A y B están completamente congeladas. No es
que vayan más lento: no ejecutan **ni una instrucción**, porque el único hilo está
adentro del `time.sleep(3)` de la tarea egoísta.

**5. ¿Con threads habría pasado lo mismo?** No. Con threads el sistema operativo
**expropia** la CPU cada pocos milisegundos y se la da a otro hilo, quiera o no el
primero. Esa es la diferencia:

| | Cooperativa (scheduler, asyncio) | Preventiva (threads) |
|---|---|---|
| Quién decide el cambio | La propia tarea, al ceder | El sistema operativo |
| Si una tarea no cede | Bloquea a todas | No pasa nada, la desalojan |
| Sincronización | Casi no hace falta | Locks por todos lados |
| Puntos de cambio | Explícitos y visibles (`yield`, `await`) | En cualquier lado |

El intercambio es claro: la cooperativa evita las race conditions porque sabés
exactamente dónde te pueden interrumpir, pero depende de que todos se porten bien.

**6. La regla** es la misma del ejercicio 7 de la clase 17: **nunca bloquear el
event loop**. Es literalmente el mismo problema —ahí el handler que hacía SHA-256
durante 2 segundos, acá el `time.sleep(3)`— porque los dos son un solo hilo
atendiendo a todos.

### Parte C: agregar tiempo

```
  total: 0.300s
  suma de las esperas: 3 tareas x 2 veces x 0.15s = 0.90s
  -> las esperas se SOLAPAN: 0.300s < 0.90s
```

**7.** `dormir(segundos)` cede devolviendo **cuándo** quiere volver:

```python
def dormir(segundos):
    yield time.perf_counter() + segundos
```

El scheduler guarda ese instante junto a la tarea y no la reanuda hasta que llegue.

**8. ¿Por qué no puede llamar a `time.sleep()`?** Porque hay **un solo hilo**:
dormirlo congela a todas las tareas, que es exactamente el bug de la parte B. La
tarea no tiene que dormir — tiene que **devolver el control** e informar cuándo
quiere que la despierten. Dormir es trabajo del scheduler, y sólo cuando **ninguna**
tarea tiene algo que hacer.

**9. El total es 0,300 s, no 0,90 s.** Las tres tareas duermen **al mismo tiempo**:
cada una cede apenas pide su espera, así que las tres esperas de 0,15 s transcurren
en paralelo. El total es el de la tarea más lenta (2 × 0,15 = 0,3 s), no la suma.

Eso es toda la ganancia de la concurrencia cooperativa para I/O: no hace el trabajo
más rápido, hace que las **esperas** se superpongan.

### Parte D: yield from

```
  con yield from:   tardo 0.300s
  sin yield from:   tardo 0.000s  (no espero: el generador nunca se ejecuto)
```

**10. ¿Qué hace `yield from dormir(espera)`?** **Delega** en el subgenerador: todo
lo que `dormir()` produzca sube al scheduler como si lo hubiera producido
`tarea_lenta` directamente, y todo lo que el scheduler mande baja a `dormir()`.
Además, cuando el subgenerador termina, `yield from` devuelve su valor de retorno.

No alcanza con `dormir(espera)` a secas porque **llamar a un generador no lo
ejecuta**: crea el objeto y lo deja ahí. Sin algo que lo itere, el cuerpo nunca
corre.

**11. ¿Qué pasa al sacarlo?** Lo medí: la tarea tarda **0,000 s** en vez de 0,300 s.
Crea el generador, lo descarta sin usar y sigue de largo — la espera no ocurre.

Y lo peor es que **no falla ruidosamente**: no hay excepción ni error, el programa
anda y sólo hace mal lo que tenía que hacer. Un generador sin iterar es un objeto
perfectamente válido que se recolecta en silencio.

Es el mismo bug que en asyncio produce el `RuntimeWarning: coroutine was never
awaited` — y ahí al menos Python avisa, que es una de las razones por las que se
agregó `async`/`await` (ejercicio 3, punto 6).

### Checklist del obligatorio

- [x] Scheduler que intercala tareas, escrito desde cero
- [x] Contador de reanudaciones (12 para 9 pasos y 3 tareas)
- [x] Probado qué pasa con una tarea que no cede, y explicado
- [x] Explicada la diferencia entre concurrencia cooperativa y preventiva
- [x] `dormir()` implementado cediendo el control, sin `time.sleep()`
- [x] Medido que las esperas se solapan (0,300 s contra 0,90 s)
- [x] Explicado qué hace `yield from` y qué pasa si se omite

---

## Ejercicio 3: El puente a async/await

**1.** Llamar a una función `async def` devuelve un objeto **corrutina**, y **no
ejecuta nada** de su cuerpo. Es exactamente lo mismo que pasa con un generador: la
llamada construye el objeto, y hace falta algo que lo impulse.

**2 y 3.** Una corrutina tiene `.send()`:

```python
async def f(): return 99
c = f()
hasattr(c, 'send')      # True
c.send(None)            # StopIteration: 99
```

Es el mismo mecanismo del ejercicio 1.3: el valor de retorno viaja en
`StopIteration.value`. Eso demuestra que las corrutinas **son** generadores por
dentro, con otra interfaz: `await` es `yield from` con otro nombre, y `asyncio.run`
es un scheduler como el que escribí en el ejercicio 2.

**4.** Que `await` funcione sobre un generador decorado con `@types.coroutine`
demuestra que las dos sintaxis son **el mismo mecanismo**. El decorador no
convierte nada: sólo marca el generador como *awaitable* para que `await` lo
acepte. Por debajo, los dos caminos terminan en el protocolo `send()`/
`StopIteration`.

**5. Traducción a sintaxis moderna:**

```python
async def buscar(id):
    conn = await abrir()
    datos = await leer(conn, id)
    return datos
```

`@asyncio.coroutine` desaparece (quedó obsoleto y se eliminó en 3.11), `def` pasa a
`async def`, y cada `yield from` pasa a `await`.

**6. ¿Por qué se introdujo `async`/`await` si `yield from` ya funcionaba?** Por dos
problemas concretos:

1. **Ambigüedad**: con `yield from` no se podía distinguir un generador que produce
   valores de una corrutina que espera I/O. Eran la misma cosa sintácticamente, y
   había que leer el cuerpo entero (o confiar en el decorador) para saber de cuál se
   trataba. Peor: un `yield` suelto dentro de una corrutina cambiaba su naturaleza
   sin que nada lo marcara.
2. **Errores silenciosos**: olvidarse el `yield from` no fallaba, simplemente no
   hacía nada — es el bug que medí en la parte D. Con `async`/`await` el intérprete
   sabe que una corrutina tiene que esperarse y avisa con
   `RuntimeWarning: coroutine was never awaited`.

A eso se suma que `async def` hace la intención explícita en la firma, y habilita
`async with` y `async for`, que con generadores no tenían forma razonable de
escribirse.

---

## Ejercicio 4: asyncio de verdad

### 4.1 El equivalente

La salida es **idéntica** a la de mi scheduler de la parte A: A, B, C, A, B, C, A,
C, C.

**1.** `asyncio.gather()` reemplaza a la `deque`, y el `while pendientes` lo
reemplaza `asyncio.run()`, que corre el event loop hasta que no quede nada
pendiente. `await asyncio.sleep(0)` cumple el papel del `yield` pelado: ceder sin
pedir ninguna espera.

**2. Sin el `await` delante de `gather`:**

```
  main termino sin esperar a nadie
  [X] paso 1/1
  _GatheringFuture exception was never retrieved
```

`gather()` programa las tareas pero no las espera, así que `main` termina de
inmediato. Después `asyncio.run()` cierra el loop y cancela lo que quedaba, y
aparece el ruido de `_GatheringFuture exception was never retrieved` con un
`CancelledError`. Es el mismo bug de la parte D del ejercicio 2, en versión
asyncio — con la diferencia de que acá al menos hace ruido.

**3. `asyncio.run()` dos veces seguidas:** **funciona**. Las dos corren
normalmente, porque cada `run()` crea su propio event loop, lo corre y lo cierra.
No hay nada que se "gaste".

Lo que **no** se puede es llamarlo **adentro** de una corrutina que ya está
corriendo:

```
RuntimeError: asyncio.run() cannot be called from a running event loop
```

Porque `run()` quiere crear un loop nuevo y ya hay uno activo en ese hilo. Para
esperar algo desde adentro se usa `await`, no `run()`.

### 4.2 Crear no es ejecutar

```
saludar() devolvio: coroutine (no imprimio nada)
aviso: RuntimeWarning: coroutine 'saludar' was never awaited
con asyncio.run():
  hola
```

**4.** La llamada sola **no imprime nada**: sólo construye el objeto corrutina. El
aviso es `RuntimeWarning: coroutine 'saludar' was never awaited`, y aparece cuando
el objeto se recolecta sin haberse esperado nunca. Con `asyncio.run()` sí se
ejecuta.

**5.** Es exactamente lo mismo que con los generadores: crear uno sin llamar a
`next()` tampoco ejecuta nada del cuerpo. En los dos casos la llamada **construye**
un objeto suspendido, y hace falta algo que lo impulse — `next()`/`send()` para el
generador, el event loop para la corrutina. La única diferencia es que Python
aprendió a avisar en el caso de las corrutinas.

### 4.3 gather

```
  orden de TERMINACION:
  [rapida] termine tras 0.1s
  [media]  termine tras 0.2s
  [lenta]  termine tras 0.3s
  orden de los RESULTADOS: ['lenta', 'rapida', 'media']
```

**6. Terminan por duración**: la de 0,1 s primero, después la de 0,2 y por último la
de 0,3. Corren en paralelo, así que el orden lo decide cuánto duerme cada una.

**7. Pero `gather` devuelve en el orden en que se le pasaron los argumentos**, no en
el que terminaron: `['lenta', 'rapida', 'media']` es el orden de la llamada. Es una
garantía importante — permite desempaquetar los resultados con confianza:

```python
a, b, c = await asyncio.gather(tarea_a(), tarea_b(), tarea_c())
```

**8. La diferencia, medida con tres corrutinas de 1 s:**

```
    gather:      1.00s
    secuencial:  3.02s
```

`gather` las lanza **todas a la vez** y espera a que terminen: el total es el de la
más lenta. El bucle con `await` adentro las corre **una tras otra**: cada `await`
espera a que esa corrutina termine antes de empezar la siguiente, y el total es la
suma.

Es el mismo resultado que midió mi scheduler en la parte C, y el error más común al
empezar con asyncio: poner `async` por todos lados y después esperar en serie, con
lo cual no se gana absolutamente nada.

---

## Ejercicio 5: Cuándo sirve y cuándo no

```
=== I/O-bound: 3 tareas que esperan 1.0s cada una ===
  secuencial (una tras otra)                  3.00s
  asyncio.gather con asyncio.sleep            1.02s
  asyncio.gather con time.sleep  <- el bug    3.00s

=== CPU-bound: 3 tareas que calculan ===
  secuencial                                  2.62s
  asyncio.gather                              2.59s
```

**1. En I/O-bound asyncio mejora 3×**: de 3,00 s a 1,02 s con tres tareas. La mejora
escala con la cantidad de tareas concurrentes, no es un factor fijo.

**2. Con `time.sleep()` adentro de la corrutina: 3,00 s**, igual que el secuencial.
No mejora nada porque `time.sleep()` **no cede el control**: bloquea el hilo
entero, y mientras tanto el event loop no puede correr ninguna otra corrutina. Es
la tarea egoísta del ejercicio 2 parte B, con otro disfraz.

La regla: `async def` no vuelve asíncrono a nada. Lo que hace a una corrutina
concurrente es **lo que espera adentro**.

**3 y 4. En CPU-bound: da igual, y un poquito peor.** 2,59 s contra 2,62 s — la
diferencia está dentro del ruido de medición, pero la expectativa teórica es que
asyncio sea **levemente más lento**, porque el trabajo real es el mismo y encima se
paga el costo de crear tareas, programarlas y pasar por el event loop. No hay nada
que solapar: no hay esperas, hay cálculo, y el cálculo ocupa el único hilo de punta
a punta.

**5. La regla en una frase:** asyncio conviene cuando el programa pasa la mayor
parte del tiempo **esperando** (red, disco, base de datos) y hay **muchas** esperas
que solapar; no sirve para nada cuando el tiempo se va en calcular.

**6. ¿Es el mismo criterio que el GIL?** **Es el mismo criterio para decidir, pero
por una razón distinta.** En los dos casos la pregunta es "¿I/O-bound o CPU-bound?",
y en los dos la respuesta para CPU-bound es "usá procesos".

Pero el motivo del límite no es el mismo:

- Los **threads** con GIL no escalan en CPU porque hay un candado que impide
  ejecutar bytecode en paralelo. El sistema operativo *podría* correrlos en varios
  núcleos; el GIL no lo deja. Si se quitara el GIL (PEP 703), escalarían.
- **asyncio** no escala en CPU porque hay **un solo hilo**, y punto. Aunque no
  existiera el GIL seguiría sin usar más de un núcleo, porque la concurrencia
  cooperativa no es paralelismo: intercala, no reparte.

Donde sí se separan es en el I/O a gran escala: 10.000 hilos esperando son
inviables (clase 14), 10.000 corrutinas son baratas (clase 17). Por eso asyncio
gana ahí aunque los threads también liberen el GIL durante el I/O.

### 5.1 Encontrar el bloqueo

**7. ¿Por qué no se solapan las cinco descargas?** Porque `urllib.request.urlopen()`
es **sincrónico**: bloquea el hilo hasta que la descarga termina. El `async def` no
cambia eso — hace que la función devuelva una corrutina, pero adentro sigue
habiendo una llamada bloqueante. Mientras está esperando la respuesta HTTP, el
event loop no puede correr las otras cuatro.

Es el caso de `time.sleep()` del punto 2, con una biblioteca real en vez de un
`sleep`. El síntoma es el mismo: el código *parece* asíncrono, no da ningún error, y
tarda exactamente lo mismo que si fuera secuencial.

**8. ¿Qué usar en su lugar?** Un cliente HTTP asíncrono: **`aiohttp`** o
**`httpx`** en modo async. Los dos ceden el control durante la espera de red, que
es lo que permite que las cinco descargas se solapen:

```python
import httpx

async def bajar(url):
    async with httpx.AsyncClient() as cliente:
        r = await cliente.get(url)
        return r.content
```

La alternativa, si hay que seguir usando la biblioteca sincrónica, es sacarla del
hilo del loop con `await asyncio.to_thread(urllib.request.urlopen, url)`.

**9. Tres llamadas bloqueantes comunes que no van adentro de una corrutina:**

1. **`time.sleep()`** — se reemplaza por `await asyncio.sleep()`.
2. **`requests` / `urllib.request`** — se reemplazan por `httpx` o `aiohttp`.
3. **`open()` y las lecturas de archivo**, además de los drivers de base de datos
   sincrónicos (`psycopg2`, `sqlite3`) y cualquier `subprocess.run()`. Se reemplazan
   por sus versiones async (`aiofiles`, `asyncpg`, `asyncio.create_subprocess_exec`)
   o se sacan a un thread con `asyncio.to_thread()`.

La regla práctica para detectarlos: si una línea adentro de un `async def` **no
tiene `await`** y puede tardar, probablemente esté bloqueando el loop. Para
encontrarlos, `loop.set_debug(True)` avisa cuando una corrutina tarda demasiado sin
ceder.
