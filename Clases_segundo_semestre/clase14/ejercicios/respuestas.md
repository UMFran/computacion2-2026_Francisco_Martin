# Clase 14: Servidores Concurrentes — Respuestas

Medido en **WSL (Ubuntu), Python 3.12.3, 32 núcleos** (`nproc` = 32).

Código: `ejercicio3_servidor.py`, `ejercicio3_zombies.py`,
`ejercicio4_sin_lock.py`, `ejercicio5_socketserver.py`, `ejercicio6_cpu.py`.

---

## Ejercicio 1: Medir las cuatro estrategias

### 1.1 La línea de base — `server_secuencial.py --lento 1`, 20 clientes

```
Completados:           20/20
Tiempo total:          20.01s
Latencia mínima:       1.005s
Latencia mediana:      10.506s
Latencia máxima:       20.002s
Throughput:            1.0 clientes/s
Nota: la latencia va de 1.00s a 20.00s — los clientes fueron atendidos en serie.
```

**1.** 20,01 s, que es exactamente lo esperado: 20 clientes × 1 s cada uno. El
servidor atiende de a uno, así que los tiempos se suman.

**2.** La mínima es 1,005 s y la máxima 20,002 s porque los 20 clientes conectan
*al mismo tiempo* pero son atendidos en fila. El primero espera sólo su propio
segundo de trabajo; el último espera a los 19 que tenía adelante más el suyo. La
mediana (10,5 s) cae justo en el medio, como corresponde a un reparto lineal.

**3.** El benchmark detecta que la latencia mínima ≈ el trabajo de un cliente y
la máxima ≈ N × ese trabajo, con las intermedias repartidas parejo. Esa escalera
es la huella de la atención en serie: si fuera concurrente, todas las latencias
rondarían 1 s.

### 1.2 Las tres concurrentes

**4. La tabla** (todas con `--lento 1` y 20 clientes):

| Servidor | Tiempo total | Latencia máx | Throughput |
|---|---|---|---|
| Secuencial | 20,01 s | 20,002 s | 1,0 cliente/s |
| Threads | 1,01 s | 1,004 s | 19,7 clientes/s |
| Fork | 1,01 s | 1,006 s | 19,7 clientes/s |
| Pool (20) | 1,07 s | 1,066 s | 18,7 clientes/s |

**5. ¿Por qué las tres concurrentes dan casi lo mismo?** Porque con 20 clientes
ninguna llega a su límite. El trabajo es un `sleep`, o sea I/O simulado: no
consume CPU, y los 20 pueden estar "trabajando" a la vez sin competir por nada.
El tiempo total es el de *un* cliente, porque todos corren en paralelo. Las
diferencias de arquitectura (costo de crear un hilo vs un proceso, tamaño del
pool) son ruido frente a 1 s de espera. El pool queda 60 ms atrás porque reparte
el trabajo entre workers y eso agrega un poco de coordinación.

**6. Sin `--lento`:**

```
server_secuencial   Tiempo total: 0.01s   Throughput: 1333.5 clientes/s
server_threads      Tiempo total: 0.02s   Throughput: 1261.8 clientes/s
server_fork         Tiempo total: 0.02s   Throughput: 1287.3 clientes/s
server_pool         Tiempo total: 0.01s   Throughput: 1496.5 clientes/s
```

**No se distinguen en absoluto**, y el secuencial llega a estar entre los más
rápidos. El parámetro cambia todo porque sin trabajo por cliente la atención dura
microsegundos: el servidor secuencial despacha los 20 antes de que ninguno llegue
a notar la espera, y lo único que se mide es el costo de crear hilos o procesos,
que la concurrencia *agrega*. De ahí la moraleja: un benchmark sin carga
realista no sólo no muestra la diferencia, la muestra al revés.

### 1.3 Escala

**9.** `ulimit -n` acota los descriptores por proceso, y ese es el techo que
encuentra el servidor de **threads**: cada cliente consume un descriptor, más
unos 8 MB de stack por hilo. El de **fork** choca antes con otro límite —memoria
y `nproc`— porque un proceso es mucho más caro que un hilo: cada uno copia el
espacio de direcciones (con copy-on-write, pero igual paga tablas de páginas y
estructuras del kernel). Por eso threads escala a más clientes que fork, aunque
los dos se queden muy lejos de lo que logra el multiplexing de la clase 17.

---

## Ejercicio 2: El pool que satura

**`--workers 5 --lento 1`, 20 clientes:**

```
Completados:           20/20
Tiempo total:          4.01s
Latencia mínima:       1.001s
Latencia mediana:      2.503s
Latencia máxima:       4.002s
Throughput:            5.0 clientes/s
```

**1.** 4,01 s = 20 clientes ÷ 5 workers × 1 s. Con el pool, el tiempo total es
`(clientes / workers) × trabajo`: los workers son el cuello de botella.

**2.** Hay **4 escalones**, uno por tanda: los primeros 5 clientes terminan a 1 s,
los siguientes 5 a 2 s, después a 3 s y a 4 s. La mediana de 2,503 s cae entre el
segundo y el tercero, como corresponde.

**3. ¿Alguno rechazado?** No: **20/20 completados**. Es la distinción importante.
Un cliente **demorado** conectó y está esperando su turno en la cola; uno
**rechazado** recibió un error (`ConnectionRefusedError`) y no va a ser atendido
nunca. Acá el pool demora pero no rechaza, porque la cola de `listen()` los
sostiene. El rechazo aparecería si esa cola se llenara.

**4. `--workers 1`:**

```
Tiempo total:          20.15s
Latencia mínima:       1.008s
Latencia máxima:       20.146s
Throughput:            1.0 clientes/s
```

Idéntico al **secuencial** (20,01 s). Tiene sentido: un pool de un worker es un
servidor secuencial con pasos de más.

**5. ¿Para qué carga sirve un pool?** Para trabajo **corto y acotado**, donde cada
petición se atiende y se va: APIs sin estado, procesamiento por lotes, consultas
rápidas. Ahí el pool da lo mejor de los dos mundos — acota el consumo de recursos
(no hay explosión de hilos con 10.000 clientes) y evita el costo de crear y
destruir todo el tiempo.

Donde falla es con **conexiones persistentes y largas**, que es lo que acabo de
medir: si cada cliente ocupa un worker durante minutos, N clientes bloquean el
servicio para el cliente N+1, por más que la máquina esté ociosa. Para eso el
modelo correcto es el multiplexing de la clase 17.

---

## Ejercicio 3: Los tres descuidos del fork (OBLIGATORIO)

### Parte A: el padre que no cierra

**1. ¿Crecen los descriptores?** Medido con `--sin-cierre-padre`, tres rondas de
30 clientes:

```
A  padre sin close()    fds: 5 -> 5    zombies: 0
```

**No crecen.** Igual que anticipa la consigna.

**2. ¿Quién cerró el descriptor?**

```
$ python3 -c "import socket, gc, os
def make(): return socket.socket().fileno()
fd = make(); gc.collect(); os.fstat(fd)"
OSError: Bad file descriptor -> el fd ya estaba cerrado
```

Lo cerró el **recolector de basura de CPython**, vía conteo de referencias. El
objeto `socket` tiene un `__del__` que llama a `close()`, y en cuanto la última
referencia desaparece el contador llega a cero y el objeto se destruye *en el
acto* — no hace falta ni esperar al `gc.collect()`.

**3. ¿Qué le pasa al `conn` de la vuelta anterior?** Al reasignar `conn` en la
siguiente vuelta del `while True`, la referencia al socket viejo se pierde. Como
nadie más lo referencia, el contador baja a cero, se destruye y se cierra solo.
Por eso el descuido no se nota.

**4 y 5. ¿Entonces el `close()` del padre es innecesario?** No, y los tres casos
lo explican:

- **En C**: `accept()` devuelve un `int`, no un objeto. No hay destructor ni
  recolector; el descriptor queda abierto hasta que el proceso termine. El leak
  es real y el servidor se queda sin descriptores.
- **Si el padre guarda las conexiones** (`activas.append(conn)`): la referencia
  sobrevive, el contador nunca llega a cero y el socket nunca se cierra. Es lo que
  mido en la parte A2.
- **En PyPy u otra implementación sin conteo de referencias**: la recolección es
  diferida, así que los descriptores se acumulan *entre* recolecciones. Con carga
  alta se agotan antes de que el recolector pase.

La conclusión es que el `close()` explícito sigue siendo correcto porque **no
depende de un detalle de implementación de CPython**. El conteo de referencias no
es parte de la especificación del lenguaje: es cómo CPython resuelve hoy la
gestión de memoria. Escribir el `close()` expresa la intención —"el padre terminó
con esta conexión"— en vez de confiar en que el recolector llegue a tiempo. Es la
misma razón por la que se usa `with` para los archivos aunque CPython los cierre
solo.

### Parte A2: el cierre que sí se nota

**6. Guardando las conexiones en una lista:**

```
fds antes:   5
Completados: 30/30
fds despues: 35
```

**Ahora sí crecen**: +30 descriptores, exactamente uno por cliente. La referencia
en la lista impide que el contador llegue a cero, así que el recolector no
interviene y el leak queda a la vista.

**7 y 8. ¿Por qué el cliente no ve el cierre?** Después del `fork()` hay **dos
copias del descriptor** apuntando a la misma conexión TCP: una en el padre y otra
en el hijo. El kernel lleva un contador de referencias sobre la descripción de
archivo abierta, y el **FIN de TCP se manda recién cuando ese contador llega a
cero**, o sea cuando se cierran *todas* las copias.

Entonces, si se mata al hijo pero el padre conserva la suya, el cliente **no se
entera de nada**: la conexión sigue abierta desde el punto de vista de TCP, y el
cliente queda esperando datos que no van a llegar, hasta su propio timeout (o para
siempre, si no lo tiene — clase 13). Desde afuera parece que el servidor se colgó.

Ese es el bug que el descriptor filtrado esconde, y la razón de fondo por la que
el `close()` del padre no es opcional: no se trata sólo de ahorrar descriptores,
sino de que el cierre de la conexión funcione.

### Parte B: los zombies

Sin handler de `SIGCHLD`, 50 clientes:

```
B  sin cosechar    fds: 5 -> 5   zombies: 50
```

**4.** Los hijos quedan en estado **`Z` (zombie)**: terminaron su ejecución pero
el kernel conserva su entrada en la tabla de procesos porque nadie leyó su código
de salida. No consumen CPU ni memoria, pero sí una entrada de la tabla y un PID.

**5.** Se acumulan: uno por cliente atendido, y cada benchmark nuevo suma los
suyos.

**6. Un servidor así durante semanas** agota la tabla de procesos del sistema. Al
llegar al límite (`kernel.pid_max`, o el `RLIMIT_NPROC` del usuario) `fork()`
empieza a fallar con `BlockingIOError: [Errno 11] Resource temporarily
unavailable`, y a partir de ahí el servidor no puede atender a nadie más. Lo peor
es que para entonces falla **todo** el sistema, no sólo el servidor, porque nadie
puede crear procesos nuevos.

### Parte C: el bucle del cosechador

Con el script de 60 hijos que mueren a la vez, **5 corridas de cada uno**:

```
=== handler SIN bucle ===
bucle=no  hijos=60  recogidos=58  zombies=3
bucle=no  hijos=60  recogidos=53  zombies=8
bucle=no  hijos=60  recogidos=54  zombies=7
bucle=no  hijos=60  recogidos=58  zombies=3
bucle=no  hijos=60  recogidos=56  zombies=5

=== handler CON bucle ===
bucle=si  hijos=60  recogidos=60  zombies=0     (las 5 corridas)
```

**8. ¿Siempre da lo mismo?** No: entre 3 y 8 zombies según la corrida. Esa
variabilidad **es** el síntoma.

**9. Con el bucle**: 60 recogidos y 0 zombies, las cinco veces. Determinista.

**10. ¿Por qué es intermitente?** Porque **las señales no se encolan**. `SIGCHLD`
es una señal estándar, no de tiempo real: el kernel lleva un solo bit de
"pendiente" por señal. Si mueren 10 hijos mientras el handler está corriendo, los
10 marcan el mismo bit y el proceso ve **una sola** señal. Un handler que recoge
un hijo por invocación deja 9 sin cosechar.

Cuántos se pierden depende de cuántas señales colapsen, y eso depende del
planificador: de ahí que el número cambie en cada corrida. Con clientes
escalonados las señales llegan de a una y el handler sin bucle da abasto, que es
por qué el bug no aparece con el benchmark normal y sí cuando mueren todos juntos.

El bucle `while True` con `WNOHANG` lo arregla porque no confía en la cantidad de
señales: en cada invocación cosecha **todos** los hijos que haya listos, hasta que
`waitpid` devuelve 0.

**11. ¿Qué hace `WNOHANG`?** Hace que `waitpid()` **no bloquee**: si no hay ningún
hijo terminado, devuelve `(0, 0)` en vez de quedarse esperando. Sin él, el bucle
`while True` del handler se bloquearía en la primera vuelta sin hijos pendientes
—y bloquearse *dentro de un handler de señal* es grave: el programa queda detenido
en el medio de lo que estuviera haciendo, con el resto de las señales enmascaradas.
En un servidor, eso significa dejar de llamar a `accept()`.

**12. ¿Cómo encontrar un bug así en producción?** Un fallo que aparece en 2 de
cada 3 corridas y sólo bajo carga no se encuentra leyendo logs:

- **Monitoreo del síntoma**: alertar sobre la cantidad de procesos en estado `Z`
  (`ps -eo stat | grep -c Z`). El crecimiento sostenido es inconfundible y no
  depende de atrapar el momento exacto.
- **Reproducir el pico**: una prueba de carga que haga morir muchos hijos
  simultáneamente, que es exactamente lo que hace `ejercicio3_zombies.py`.
  Reproducir en 5 corridas lo que en producción pasa una vez por semana.
- **Correr muchas veces**: un test que corre 100 veces convierte un fallo del 30 %
  en una certeza estadística. Un test que corre una vez no prueba nada.
- **Revisión de código**: para los patrones conocidos —cosechar sin bucle, `+=`
  sin lock— la revisión es más barata que cualquier instrumentación.

### Parte D: la alternativa

```
D  SIG_IGN    zombies: 0
```

**10.** Con `signal.signal(signal.SIGCHLD, signal.SIG_IGN)` **no quedan zombies**.
Quien los cosecha ahora es el **kernel**: cuando `SIGCHLD` está explícitamente
ignorado, POSIX especifica que el sistema no cree entradas zombie, y los hijos se
limpian solos al terminar.

Es más simple y no tiene el bug del bucle. La contra es que se pierde el código de
salida de los hijos: si hiciera falta saber si un hijo falló, hay que volver al
handler explícito.

### Checklist del obligatorio

- [x] Mostrar el crecimiento de descriptores cuando el padre no cierra `conn`
      (parte A2: 5 → 35 con 30 clientes)
- [x] Explicar por qué el cliente no ve el cierre de la conexión
- [x] Mostrar zombies acumulándose sin handler de `SIGCHLD` (50 clientes → 50 zombies)
- [x] Mostrar que un cosechador sin bucle deja zombies bajo carga (3 a 8 por corrida)
- [x] Explicar qué hace `WNOHANG` y por qué es necesario
- [x] Verificar que `SIG_IGN` también funciona, y decir quién cosecha (el kernel)

---

## Ejercicio 4: Race conditions reales

Sacando el `with lock:` de las dos secciones, con `--dormir` (un `sleep(0.0001)`
entre leer y escribir) y 200 clientes:

```
Atendidos: 200
clientes_activos al final: -5 (deberia ser 0)
Pico de simultaneos: 8
```

**2 y 3. ¿Vuelve a cero?** No: terminó en **-5**. Cada cliente suma 1 al entrar y
resta 1 al salir, así que el saldo debería ser exactamente 0. El `-5` significa
que se perdieron 5 incrementos (dos hilos leyeron el mismo valor y el segundo pisó
el resultado del primero).

Sin el `sleep` el fallo aparece a veces y con menos diferencia; el `sleep` agranda
la ventana entre la lectura y la escritura, que es donde entra el otro hilo.

**4. ¿Por qué `clientes_activos += 1` no es atómico?** Porque son **tres
operaciones**, no una: leer el valor actual, sumarle 1, escribir el resultado. En
bytecode son `LOAD_GLOBAL`, `LOAD_CONST`, `BINARY_OP`, `STORE_GLOBAL`, y el
intérprete puede cambiar de hilo entre cualquiera de ellas.

El entrelazado que pierde un incremento es el mismo de la cuenta bancaria de la
clase 11:

```
hilo A: lee 5
hilo B: lee 5          <- lee antes de que A escriba
hilo A: escribe 6
hilo B: escribe 6      <- pisa el 6 de A; deberia ser 7
```

El GIL no salva de esto: garantiza que un bytecode no se parta por la mitad, pero
no que una secuencia de bytecodes sea indivisible. Esa garantía la da el `Lock`.

**5. ¿Por qué `fork()` no necesita el lock?** Porque los procesos **no comparten
memoria**. Después del `fork()`, cada hijo recibe su propia copia del espacio de
direcciones (con copy-on-write): si modifica `clientes_activos`, modifica *su*
copia, y el padre no se entera. No hay dato compartido, así que no hay carrera.

El costo es el otro lado de la misma moneda: tampoco se puede llevar un contador
global de verdad. Para eso haría falta memoria compartida explícita
(`multiprocessing.Value`, `Manager`) de la clase 9 — y ahí vuelve a hacer falta el
lock.

---

## Ejercicio 5: socketserver

Con `--lento 1` y 20 clientes:

| Implementación | Tiempo total | Latencia máx |
|---|---|---|
| `server_threads.py` (a mano) | 1,01 s | 1,004 s |
| `ThreadingTCPServer` | 1,01 s | 1,008 s |
| `ForkingTCPServer` | 1,23 s | 1,220 s |

**1.** `ThreadingTCPServer` da **exactamente lo mismo** que el servidor escrito a
mano, en unas 20 líneas en vez de 60. No hay penalidad por usar la biblioteca.

**2. ¿Qué resuelven `rfile`/`wfile`?** El **framing** de la clase 13. Envuelven el
socket con `makefile()` y dan un objeto tipo archivo, así que `for linea in
self.rfile` entrega líneas completas: el buffer que había que escribir a mano para
juntar los pedazos de `recv()` ya está hecho adentro.

Aclaración sobre mi implementación: `benchmark.py` manda 256 bytes **sin** `\n`,
así que iterar por líneas se quedaría esperando un salto que no llega y el cliente
se iría por timeout. Por eso el handler usa `self.rfile.read1(4096)`, que devuelve
lo que haya disponible igual que `recv()`. El framing por líneas sigue estando
disponible, lo que pasa es que este benchmark no habla un protocolo de líneas.

**3. `ForkingTCPServer`:** 1,23 s contra 1,01 s, un ~20 % más lento. La diferencia
es el costo de crear un proceso por cliente en vez de un hilo. Con sólo 20
clientes y 1 s de trabajo es poco, pero crece con la cantidad de clientes.

**4. El bucle de `accept()` en el fuente:** sí, se parece mucho a lo escrito a
mano, con un detalle interesante — `serve_forever()` **no** llama directamente a
`accept()`, sino que usa un selector:

```python
with _ServerSelector() as selector:
    selector.register(self, selectors.EVENT_READ)
    while not self.__shutdown_request:
        ready = selector.select(poll_interval)
```

O sea que `socketserver` ya usa multiplexing (clase 17), pero sólo para **una**
cosa: poder despertarse cada `poll_interval` y revisar si le pidieron parar. Esa
es la diferencia con la clase 17, donde el selector vigila *todas* las conexiones.

**5. ¿Qué justifica haber escrito las estrategias a mano?** Que `socketserver`
esconde exactamente lo que había que entender. Los tres descuidos del ejercicio 3
—el `close()` del padre, la cosecha de zombies, el bucle del cosechador— están
resueltos adentro de `ForkingMixIn`, y quien sólo usa la biblioteca no sabe que
existen ni por qué importan. El día que haya que diagnosticar por qué un cliente
no ve cerrarse una conexión, o por qué se acumulan procesos `Z`, el conocimiento
no sale del manual del framework.

Además, la decisión de arquitectura sigue siendo propia: `socketserver` ofrece
threads y fork, pero no dice cuál conviene ni dónde se rompe cada uno. Eso es
justamente lo que miden los ejercicios 1, 2 y 6.

---

## Ejercicio 6: Un servidor que hace trabajo real

`trabajo_cpu(2_000_000)` por cliente, 10 clientes, en una máquina de **32 núcleos**:

| | Tiempo total | Latencia mín | Latencia máx | Throughput |
|---|---|---|---|---|
| Threads | 0,71 s | 0,205 s | 0,706 s | 14,1 clientes/s |
| Fork | 0,10 s | 0,072 s | 0,100 s | 98,3 clientes/s |

**1 y 2. ¿Escala?** Con threads **no**: 0,71 s para 10 clientes cuando uno solo
tarda ~0,07 s de CPU. Con fork **sí**: 0,10 s, prácticamente lo que tarda un
cliente solo. Fork es **7 veces más rápido**.

**3. La diferencia es el GIL.** `trabajo_cpu` es un bucle de Python puro, que no
suelta el GIL en ningún momento. Los 10 hilos existen y el sistema operativo los
planifica, pero sólo uno puede ejecutar bytecode a la vez: se turnan, y el trabajo
total termina siendo la suma, no el máximo. Los otros 31 núcleos miran.

Con `fork()` cada cliente corre en un **proceso** distinto, y cada proceso tiene su
propio intérprete y su propio GIL. Ahí sí los 10 corren de verdad en paralelo, en
10 núcleos distintos.

Se nota incluso en la latencia mínima: 0,205 s con threads contra 0,072 s con
fork. Hasta el primer cliente sale más lento, porque desde el arranque compite por
el GIL con los otros nueve.

Esto invierte la conclusión del ejercicio 1, donde las tres estrategias daban
igual. La diferencia es qué simula el trabajo: `sleep` **libera** el GIL (es I/O),
un bucle aritmético **no**.

**4. ¿Tiene GIL este Python?**

```
$ python3 -c "import sys; print(sys._is_gil_enabled())"
AttributeError: module 'sys' has no attribute '_is_gil_enabled'
```

Esta es Python **3.12.3**, y `sys._is_gil_enabled()` existe recién desde 3.13,
que es cuando apareció el build free-threaded (PEP 703). Que el atributo no exista
ya responde la pregunta: es un build con GIL.

**5. Con un build free-threaded:**

- **Cambiaría el punto 1**: los hilos podrían ejecutar bytecode en paralelo de
  verdad, así que el servidor de threads se acercaría mucho al de fork. Es
  exactamente el problema que PEP 703 quiere resolver.
- **No cambiaría** respecto del fork el **aislamiento**: los hilos siguen
  compartiendo memoria, así que todas las race conditions del ejercicio 4 siguen
  ahí —de hecho se vuelven *más* probables, porque desaparece la serialización
  accidental que el GIL regalaba. Y un crash sigue llevándose el proceso entero
  con todos sus clientes, mientras que con fork cada cliente está aislado.

O sea que free-threading cierra la brecha de rendimiento pero no la de robustez:
seguir eligiendo procesos tiene sentido cuando lo que se busca es aislamiento.
