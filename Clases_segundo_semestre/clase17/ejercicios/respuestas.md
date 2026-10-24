# Clase 17: I/O Multiplexing — Respuestas

Medido en **WSL (Ubuntu), Python 3.12.3**, `ulimit -n` = 65535.

Código: `ejercicio1.py` (busy-wait), `ejercicio4.py` (selectors),
`ejercicio6.py` (chat), `ejercicio7.py` (CPU en el event loop).

---

## Ejercicio 0: Direcciones en el código

### 0.1 Misma red o no

```
192.168.1.37 in 192.168.1.0/24  -> True
192.168.2.10 in 192.168.1.0/24  -> False
```

**1. ¿Qué hace distinto el sistema?** Si el destino está en la **misma red**, lo
entrega directo: busca la dirección MAC con ARP y manda la trama a esa máquina. Si
está en **otra red**, se la entrega al **gateway** —usando la MAC del gateway pero
la IP del destino final— para que la enrute. Es la decisión que toma por cada
paquete, y es lo que explica la tabla de `ip route` de la clase 12.

**2. Docker** usa `172.17.0.0/16` para `docker0`. Los contenedores se ven entre sí
sin configurar nada porque están todos en esa misma red virtual: para ellos los
demás contenedores son "vecinos de segmento" y se alcanzan directo, sin pasar por
ningún router.

### 0.2 La tupla de IPv6

```
getsockname(): ('::1', 55801, 0, 0) -> 4 elementos
host, puerto = s.getsockname()
ValueError: too many values to unpack (expected 2)
forma correcta: ('::1', 55801)
```

**3.** Devuelve **cuatro** elementos: `(host, puerto, flowinfo, scope_id)`. Los dos
últimos son específicos de IPv6 — `flowinfo` para etiquetado de flujos y `scope_id`
para desambiguar direcciones link-local, que pueden repetirse entre interfaces.

**4. El error** es `ValueError: too many values to unpack (expected 2)`. Lo que
anda con las dos familias es tomar una rebanada:

```python
host, puerto = sock.getsockname()[:2]
```

**5. ¿Por qué no aparece con IPv4?** Porque ahí la tupla tiene exactamente dos
elementos y el desempaquetado funciona. El bug queda latente hasta que el programa
se encuentra con un socket IPv6 — y como muchas máquinas resuelven primero por
IPv6, aparece en producción en el primer entorno dual-stack.

### 0.3 getaddrinfo

```
AF_INET   ('142.251.128.238', 80)
AF_INET6  ('2800:3f0:4002:80b::200e', 80, 0, 0)
```

**6.** Devuelve **las dos** familias. En esta máquina salió IPv4 primero; el orden
lo decide el sistema según RFC 6724 y la configuración local, así que no conviene
darlo por sentado.

**7. ¿Por qué probar en orden?** Porque que una dirección esté en la lista no
significa que sea alcanzable. Una máquina puede tener IPv6 configurado pero sin
ruta real a Internet: el intento falla o da timeout, y hay que pasar a la
siguiente. Quedarse con `resultados[0]` es el bug clásico — anda en la máquina del
que lo escribió y falla en otra red.

**8. `socket.create_connection()`** hace exactamente ese bucle: llama a
`getaddrinfo`, prueba cada dirección en orden, cierra las que fallan y devuelve la
primera que conecte, relanzando la última excepción si no anda ninguna. También
crea el socket con la familia correcta de cada entrada.

### 0.4 Dual-stack

**9 y 10.** Con `IPV6_V6ONLY = 0` el socket IPv6 acepta las dos familias. Un
cliente IPv6 se ve como `::1`; uno **IPv4 se ve mapeado** como
`::ffff:127.0.0.1`. El prefijo es `::ffff:/96`, y eso importa mucho si el servidor
filtra por IP: una lista de direcciones permitidas escrita en IPv4 plano **no va a
matchear** con la forma mapeada, y el filtro deja pasar (o bloquea) a quien no
debía.

**11.** Con `IPV6_V6ONLY = 1` el cliente IPv4 **no puede conectarse**: el socket
atiende sólo IPv6.

**12. ¿Por qué ponerlo explícito?** Porque el valor por defecto **varía según el
sistema**: Linux suele traerlo en 0 (dual-stack) y los BSD en 1. Un servidor que
depende del default anda en una máquina y en otra deja afuera a la mitad de los
clientes, sin ningún error que lo explique. Escribirlo cuesta una línea y elimina
la ambigüedad.

---

## Ejercicio 1: Ver el problema antes de la solución

**1.** Sí, `ejercicio1.py` funciona: atiende varios clientes a la vez con sockets
no bloqueantes y sin threads.

**2 y 3. ¿Por qué consume CPU sin nadie conectado?** Porque el `while True` nunca
se detiene. `accept()` sobre un socket no bloqueante lanza `BlockingIOError`
inmediatamente si no hay nadie, el `except` lo descarta, y el bucle vuelve a
intentar — millones de veces por segundo. El proceso está **siempre ejecutable**,
así que el planificador le da todo el tiempo de CPU que puede: un núcleo al 100 %
sin hacer absolutamente nada útil. Es el mismo *busy loop* del `recv()` sin chequeo
de cierre de la clase 13.

**4. Con `servidor_select.py`** el consumo es **0 %**. La diferencia es que
`select()` **bloquea**: el kernel saca el proceso de la cola de ejecutables y lo
despierta recién cuando alguno de los sockets vigilados tiene algo. Mientras tanto
el proceso duerme y no consume nada.

Ese es el punto de todo el multiplexing: no es "revisar más rápido", es **dejar de
revisar** y que el kernel avise.

**5.** En un servidor secuencial, si el primer cliente conectaba y no mandaba nada,
el servidor quedaba bloqueado en `recv()` y **nadie más era atendido** (el problema
del ejercicio 6 de la clase 13). `select()` lo resuelve sin threads porque no
espera por *un* socket: espera por **cualquiera** del conjunto. Un cliente callado
simplemente nunca aparece en la lista de listos, y los demás se atienden igual.

---

## Ejercicio 2: select() en detalle

**1. ¿Cuántos hilos?** Uno solo: `ls /proc/$(pgrep -f servidor_select)/task | wc -l`
da **1**. Es la comparación directa contra la clase 14, donde cada cliente costaba
un hilo o un proceso.

**2.** El tercer cliente responde sin esperar a los otros dos, porque `select()`
devuelve **sólo los que tienen datos**. Los otros dos no están listos, así que ni
se los toca.

**3.** Al matar un cliente, `recv()` devuelve `b''` y el servidor imprime
`- cliente (...)`. La línea que lo detecta es el `else` del `if datos:`.

### 2.2 El bug de no remover

**4 y 5.** Comentando `vigilados.remove(sock)`, al cerrar el cliente el servidor
**gira infinitamente** consumiendo 100 % de CPU. La razón: un socket cerrado está
**siempre listo para leer** —`select()` lo reporta en cada vuelta— y cada `recv()`
devuelve `b''` al instante. El bucle no bloquea nunca.

Es el mismo bug del `recv()` sin chequeo de cierre de la clase 13, pero una capa
más arriba: ahí el síntoma era un `recv()` que no bloqueaba, acá es un `select()`
que no bloquea.

### 2.3 El límite de FD_SETSIZE

```
fd: 1103
select -> ValueError: filedescriptor out of range in select()
poll   -> [(1103, 20)]   (no falla)
```

**7.** `ValueError: filedescriptor out of range in select()`, vigilando **un solo
socket**.

**8.** Entonces el límite de `select()` **no es la cantidad** de descriptores sino
**el número de cada uno**: cualquier fd ≥ 1024 (`FD_SETSIZE`) lo rompe, aunque se
vigile uno solo. Viene de la implementación: `fd_set` es un mapa de bits de tamaño
fijo, y el fd se usa como índice.

**9. `poll()` no falla**: devolvió `[(1103, 20)]`. Usa un array de estructuras en
vez de un mapa de bits, así que no tiene techo por número de descriptor.

**10. ¿Por qué es difícil de encontrar?** Porque en desarrollo el proceso abre
pocos archivos y los fd quedan por debajo de 1024, así que **nunca falla**. En
producción, con más conexiones, logs, pools de base de datos y archivos abiertos,
los números trepan y el programa empieza a fallar — y lo hace de forma
desconcertante, porque el error aparece en un socket cualquiera y no guarda
relación con la cantidad de sockets vigilados. Es un límite que depende del
*estado global del proceso*, no del código que falla.

---

## Ejercicio 3: Comparar los tres (OBLIGATORIO)

### Parte A: el benchmark

**1. La tabla de mi máquina** (microsegundos por llamada, 3 sockets con datos
listos, promedio de 200 llamadas):

| conexiones | select | poll | epoll |
|---|---|---|---|
| 100 | 8,0 | 4,3 | 0,7 |
| 500 | 41,2 | 19,9 | 0,7 |
| 1000 | falla (ValueError) | 47,4 | 0,7 |
| 2000 | falla (ValueError) | 116,1 | 0,7 |
| 5000 | falla (ValueError) | 306,4 | 0,7 |

**2. Crecimiento de `poll()` entre 100 y 5000:** de 4,3 a 306,4 µs, un factor de
**71×** para 50× más conexiones. Es lineal (con un poco de penalidad extra por
caché), o sea **O(n)**.

**3. `epoll`:** **0,7 µs en todos los casos**, de 100 a 5000 conexiones. Plano. El
costo no depende del total vigilado sino de cuántos están listos, que siempre son 3.

**4. `select()` falla a partir de 1000 conexiones**, y coincide exactamente con lo
del ejercicio 2.3: no es que no soporte 1000 sockets, es que al abrir 1000 sockets
algún descriptor supera 1023 y revienta `FD_SETSIZE`.

### Parte B: entender el porqué

**5. ¿Por qué 3 activos de 5000 es realista?** Porque en un servidor web la mayoría
de las conexiones están **ociosas** casi todo el tiempo: con `keep-alive`, un
navegador deja la conexión abierta entre pedido y pedido, el usuario está leyendo
la página, y no llega un solo byte. De 10.000 conexiones abiertas, en un instante
dado un puñado tiene datos. Esa desproporción es lo que define el problema C10K.

**6. O(n) contra O(listos):**

- `poll()` recibe **toda la lista** de descriptores en cada llamada. El kernel la
  recorre entera, chequea el estado de cada uno y arma la respuesta. Con 5000
  sockets hace 5000 chequeos para encontrar 3, **en cada llamada**. Y además copia
  la lista entera de usuario a kernel y de vuelta.
- `epoll` mantiene el conjunto **registrado en el kernel** entre llamadas: se
  registra una vez con `epoll_ctl` y después `epoll_wait` sólo devuelve los que ya
  están listos. El kernel no recorre nada, porque los va marcando a medida que
  llegan los eventos. El costo es proporcional a los **listos**, no al total.

La diferencia de fondo es dónde vive el estado: `poll` no recuerda nada entre
llamadas, `epoll` sí.

**7. Con `ACTIVOS = 2500`** (la mitad de 5000):

| conexiones | poll | epoll |
|---|---|---|
| 1000 | 72,2 | **117,7** |
| 5000 | 362,7 | **129,6** |

La ventaja **se achica muchísimo**, y con 1000 conexiones `epoll` llega a ser
**más lento que `poll`** (117,7 contra 72,2 µs). Tiene sentido: si casi todos están
listos, O(listos) ≈ O(n) y epoll pierde su ventaja, pero sigue pagando el costo
extra de armar y devolver la lista de eventos. Su ganancia depende por completo de
que la mayoría esté ociosa.

### Parte C: el caso donde no importa

**8. Con 10, 50 y 100 conexiones:**

| conexiones | select | poll | epoll |
|---|---|---|---|
| 10 | 1,8 | 0,7 | 0,8 |
| 50 | 4,6 | 2,5 | 0,7 |
| 100 | 8,4 | 4,4 | 0,7 |

Con 10 conexiones `epoll` (0,8 µs) es **igual o peor** que `poll` (0,7 µs). No vale
la pena: la diferencia es de nanosegundos y el código es más complicado.

**9. ¿Cuándo NO tiene sentido multiplexar?** Cuando las conexiones son **pocas**
(decenas o pocos cientos) o cuando están **casi todas activas**. Ahí un hilo por
cliente de la clase 14 es más simple, más fácil de depurar, y aprovecha varios
núcleos — cosa que el event loop de un hilo no hace (ejercicio 7).

El multiplexing gana cuando hay **muchas conexiones mayormente ociosas**, que es
justamente donde los threads se rompen: 10.000 hilos son ~80 GB de stacks y un
costo de cambio de contexto enorme, mientras que 10.000 fds en un `epoll` son
nada.

### Parte D: nginx contra Apache

Apache en su modelo clásico usa **un proceso o hilo por conexión**. Con 10.000
clientes conectados eso son 10.000 hilos: a ~8 MB de stack cada uno son unos 80 GB
de memoria virtual, más el costo de que el planificador tenga que repartir la CPU
entre 10.000 ejecutables. Y la mayoría no está haciendo nada: con `keep-alive`
están esperando el próximo pedido del usuario. Se paga un hilo entero por conexión
ociosa.

Nginx usa **un event loop con `epoll`** y unos pocos procesos, uno por núcleo. Una
conexión ociosa no cuesta un hilo: cuesta una entrada en una estructura del kernel,
unos cientos de bytes. Y mis números explican por qué eso escala: con 5000
conexiones y pocas activas, `epoll` tarda **0,7 µs** por llamada contra los
**306,4 µs** de `poll` — 437 veces menos— y sobre todo **no crece**: es igual de
rápido con 100 que con 5000.

Esa combinación —memoria constante por conexión y costo constante por vuelta del
bucle— es la que le permite a nginx sostener decenas de miles de conexiones en una
máquina donde Apache se queda sin memoria antes. El límite deja de ser la
arquitectura del servidor y pasa a ser el ancho de banda o la CPU del trabajo real.

La salvedad está en el punto 7: si las conexiones estuvieran **todas activas**, la
ventaja desaparecería, y ahí el modelo de hilos vuelve a ser competitivo porque al
menos usa todos los núcleos.

### Checklist del obligatorio

- [x] Tabla con los números de mi máquina
- [x] Factor de crecimiento de `poll` calculado (71× para 50× conexiones)
- [x] Comportamiento de `epoll` descrito y explicado (plano, 0,7 µs)
- [x] Punto donde falla `select`, y por qué (valor del fd ≥ 1024, no cantidad)
- [x] Explicación de O(n) contra O(listos)
- [x] Prueba con `ACTIVOS` alto y su interpretación (epoll pierde la ventaja)
- [x] Conclusión escrita sobre nginx contra Apache

---

## Ejercicio 4: De select a selectors

Está en `ejercicio4.py`. Probado: tres clientes, eco correcto.

**1. ¿Qué desaparece?**

- La lista **`vigilados`**: el selector lleva el registro adentro, y
  `register`/`unregister` la mantienen.
- El diccionario **`direcciones`**: `register()` acepta un parámetro `data` que
  viaja con cada evento, así que la dirección se guarda ahí.
- El **`if sock is servidor`**: cada socket se registra con su propio handler, y el
  bucle sólo llama a `clave.data(...)`. Desaparece el despacho a mano.

**2. `DefaultSelector` en mi máquina:** `EpollSelector`. Elige la mejor
implementación disponible del sistema — `epoll` en Linux, `kqueue` en BSD/macOS,
`select` en Windows.

**3. Forzando `SelectSelector`:** con pocos clientes **no cambia nada**
observable, anda igual. Lo que vuelve es el **límite de fds**: hereda la
restricción de `FD_SETSIZE` del ejercicio 2.3, así que se rompe cuando algún
descriptor supera 1023. Por eso conviene el `DefaultSelector`, salvo que haya una
razón concreta.

**4. Sacando el `sel.unregister(conn)` antes del `close()`:** el síntoma es que el
selector queda con un descriptor **cerrado** registrado. En Linux, `epoll` lo saca
solo cuando el fd se cierra, pero el objeto `SelectorKey` queda en el mapa interno
de Python, y `select()` empieza a tirar `OSError: [Errno 9] Bad file descriptor` o
`KeyError` al intentar resolverlo. Con `SelectSelector` el síntoma es más directo:
`select()` falla con *bad file descriptor* y el servidor se cae.

Por eso el orden es siempre `unregister()` y después `close()`: el selector
necesita el fd **vivo** para poder darlo de baja.

---

## Ejercicio 5: Escritura no bloqueante

**1. ¿Por qué `send()` y no `sendall()`?** Porque en la clase 13 el socket era
**bloqueante** y había un hilo por cliente: que `sendall()` bloqueara hasta mandar
todo era exactamente lo deseable, porque sólo frenaba a ese cliente.

Acá es al revés: hay **un solo hilo para todos**. Si `sendall()` se bloquea porque
el buffer de un cliente está lleno, **congela el event loop entero** y los otros
999 clientes dejan de ser atendidos. Por eso se usa `send()`, que manda lo que
entre y vuelve enseguida, y lo que sobra queda en el buffer de salida para el
próximo `EVENT_WRITE`.

La recomendación no se contradice: cambió el contexto. Con un hilo por cliente,
bloquear es aceptable; en un event loop, bloquear es inaceptable.

**2. ¿Y si registráramos `EVENT_WRITE` permanentemente?** El bucle giraría al
100 % de CPU. Un socket sin datos pendientes está **casi siempre listo para
escribir**, así que `select()` lo reportaría en cada vuelta y volvería de
inmediato. Es el mismo busy loop del ejercicio 1, por otro camino.

De ahí la regla: vigilar `EVENT_WRITE` **sólo mientras haya algo encolado**, y
volver a `EVENT_READ` solo en cuanto el buffer se vacía. Es exactamente lo que hace
el `if not salida.get(conn)` de `chat.py`.

**3. Un cliente lento que no lee:** con `sendall()`, el hilo único se bloquea
tratando de escribirle y **los otros 999 dejan de ser atendidos** — un solo cliente
lento, o malicioso, tumba el servicio entero. Con el esquema de buffer +
`EVENT_WRITE`, ese cliente simplemente acumula bytes en su buffer de salida y el
loop sigue atendiendo a todos los demás.

**4. ¿Dónde crece la memoria?** En el diccionario `salida`: los bytes que no se
pudieron mandar se acumulan ahí sin límite. Un cliente que nunca lee hace crecer su
entrada indefinidamente hasta agotar la memoria del servidor — y como es un
diccionario del proceso, se lleva puestos a todos.

Para protegerse hace falta un **tope por cliente**: si `len(salida[conn])` supera
cierto umbral, se lo desconecta (es lo que hacen nginx y los servidores reales, con
nombres como *write buffer limit*). También se puede dejar de leer de ese cliente
mientras tenga escritura pendiente, para no generar más respuestas que no puede
recibir — contrapresión.

---

## Ejercicio 6: Chat multiusuario

Está en `ejercicio6.py`, con `/nick`, `/lista` y el framing arreglado.

**1. ¿Por qué no necesita lock?** Porque todo corre en **un solo hilo**. Cuando A
manda un mensaje y el servidor escribe en los sockets de B y C, no hay ningún otro
hilo que pueda estar modificando `clientes` o `salida` al mismo tiempo: el event
loop atiende un evento por vez, de principio a fin, antes de pasar al siguiente.

Con threads haría falta un lock porque un cliente podría desconectarse —y modificar
el diccionario— justo mientras otro hilo lo está recorriendo, con el
`RuntimeError: dictionary changed size during iteration` como mejor caso y una
race condition silenciosa como peor caso.

Es el intercambio central del modelo: se gana no tener que sincronizar nada, y se
paga no poder usar más de un núcleo (ejercicio 7).

**2. ¿Por qué encolar en vez de enviar directo?** Para no bloquear el loop. Si
`difundir()` hiciera `sendall()` sobre cada cliente y uno tuviera el buffer lleno,
la llamada se quedaría esperando y **todo el chat se congelaría** por culpa de un
solo cliente lento. Encolando, `difundir()` siempre vuelve enseguida y el envío
real se hace cuando el selector avisa que ese socket acepta datos.

**5 y 6. El framing.** No, **no es cierto** que cada `recv()` traiga una línea
completa: es la misma suposición equivocada de la clase 13. Se rompe en los dos
extremos — un `recv()` puede traer **media línea** (el mensaje queda cortado y se
procesa incompleto) o **varias líneas juntas** (se procesan como una sola, y los
comandos del medio se pierden).

Lo arreglé con un buffer por cliente (`entrada[conn]`) que acumula entre llamadas y
sólo procesa las líneas completas. Probado en los dos casos:

```
  /nick byte por byte ->  b'* ahora sos fran\n'
  /lista              ->  b'* conectados (1): fran\n'
  dos /lista juntos   ->  b'* conectados (1): fran\n* conectados (1): fran\n'
```

Mandando `/nick fran\n` **byte por byte** funciona igual, y mandando
`/lista\n/lista\n` en **un solo `sendall`** salen las dos respuestas. Son
exactamente los dos casos extremos del ejercicio 3 de la clase 13.

---

## Ejercicio 7: El costo del hilo único

Está en `ejercicio7.py`: el handler hace 3.000.000 de SHA-256 encadenados, ~2 s de
CPU.

**1. ¿Responde el segundo cliente?** **No.** Mientras el handler del primero está
calculando, el event loop no vuelve a `sel.select()`, así que no se entera de que
el segundo mandó algo. El segundo espera los ~2 segundos completos y recién después
es atendido.

**2. ¿Pasa lo mismo con `server_threads.py`?** No: ahí cada cliente tiene su hilo y
el sistema operativo **expropia** la CPU cada pocos milisegundos, así que los dos
avanzan. Van a tardar más que uno solo (el GIL serializa el bytecode, como medí en
la clase 14), pero el segundo **recibe atención** desde el principio en vez de
esperar a que el primero termine.

**3. La regla:** en un event loop **nunca hay que bloquear**. Cualquier operación
que tarde —cálculo pesado, lectura de disco, una llamada de red sincrónica— frena
a **todos** los clientes, porque no hay nadie más que atienda. La concurrencia es
**cooperativa**: cada handler tiene que devolver el control rápido, y si no lo hace
no hay ningún mecanismo que lo obligue.

Es exactamente lo mismo que vuelve a aparecer en la clase 18 con la tarea egoísta
del scheduler, y en la 19 con el `async def` que llama a una biblioteca
bloqueante.

**4. ¿Cómo resolverlo sin abandonar el event loop?** Sacando el trabajo pesado del
hilo del loop, no eliminándolo:

- **Un pool de hilos o procesos** para el cálculo: el handler delega y registra un
  callback para cuando el resultado esté listo. Para CPU-bound tiene que ser un
  pool de **procesos**, porque el GIL anula el beneficio de los hilos (clase 14).
  Es lo que hace `loop.run_in_executor()` en asyncio.
- **Partir el trabajo en pedazos** que cedan el control entre uno y otro, si el
  cálculo lo permite.
- **Una cola de trabajos** con workers aparte: el loop sólo recibe pedidos y
  entrega respuestas, y el cómputo pasa a otro proceso o a otra máquina.

La idea común es la misma: el event loop sirve para **coordinar I/O**, no para
hacer cálculo. Mezclar las dos cosas es lo que lo rompe.
