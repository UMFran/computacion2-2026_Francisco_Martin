# Clase 15: UDP — Respuestas

Código: `ejercicio2.py`, `ejercicio3.py` (obligatorio), `ejercicio4.py`,
`ejercicio5.py`, `ejercicio6.py`.

Varias respuestas cambian según el sistema operativo, así que corrí lo mismo en
**Windows 11** y en **WSL (Ubuntu)** y comparo.

---

## Ejercicio 1: Primer contacto con datagramas

**1. ¿Qué devuelve `recvfrom()` además de los datos?** La **dirección del
remitente**, como tupla `(ip, puerto)`. Hace falta porque el socket no está
conectado a nadie: un mismo socket recibe de todos, así que la única forma de
saber a quién contestarle es que cada datagrama venga con su remitente. En TCP esa
información está implícita en la conexión.

**2. ¿Cambia el puerto efímero?** Sí, cada corrida del cliente usa uno distinto.
El cliente crea un socket nuevo y no hace `bind()` explícito, así que el kernel le
asigna un puerto libre al mandar el primer datagrama. Al terminar el proceso el
puerto se libera y la próxima corrida recibe otro.

**3. ¿Y si matás el servidor?** El cliente manda igual (UDP no avisa nada al
enviar) y se queda esperando una respuesta que nunca llega, hasta que vence el
`settimeout(2.0)`: dos segundos. En Linux puede además llegar un ICMP *port
unreachable* que lo convierte en `ConnectionRefusedError` inmediato — ver el
ejercicio 4, donde eso se estudia en detalle.

**4. Sin el `settimeout(2.0)`:** espera **para siempre**. Hay que cortar con
Ctrl+C. Es el mismo problema de la clase 13: sin timeout no hay forma de
distinguir "está tardando" de "no va a venir nunca", y en UDP es peor porque no
hay conexión que se rompa para avisar.

**7. ¿Qué llamadas desaparecen respecto de `echo_server.py`?** `listen()` y
`accept()`. Y con ellas desaparece el socket por cliente: en TCP `accept()`
devolvía un socket nuevo por conversación, acá hay **uno solo** para todos.

**8. ¿Por qué no necesita un socket por cliente?** Porque no hay conexión que
representar. La cuádrupla de la clase 12 identifica una conexión TCP, y el sistema
necesita un socket por cada una para saber a qué conversación pertenece cada byte.
En UDP no hay conversación: cada datagrama es independiente y trae su propio
remitente, así que un socket atado a `(ip_local, puerto_local)` alcanza para
recibir de cualquiera.

**9. ¿Hace falta concurrencia?** Casi nunca, y por eso el problema de la clase 14
prácticamente desaparece. El motivo es que en TCP un cliente "ocupa" el servidor
mientras la conexión está abierta: puede conectarse y no mandar nada durante
minutos, y el servidor secuencial queda trabado en `recv()`. En UDP no existe esa
ocupación — el servidor hace `recvfrom()`, atiende el datagrama y vuelve a
`recvfrom()`. Un cliente lento no puede bloquear a los demás porque no hay nada
que mantener abierto.

El problema vuelve si el *procesamiento* de un datagrama es lento: ahí sí los
demás esperan, y hace falta concurrencia. Pero es un problema de CPU, no de
clientes que se quedan colgados.

---

## Ejercicio 2: Los límites del datagrama

**1 y 2. Tres `sendto()` → tres `recvfrom()`.** Lo verifiqué en la clase 12 con
`udp_srv.py`:

```
recv: b'HOLA' de ('127.0.0.1', 56389)
recv: b'COMO' de ('127.0.0.1', 56389)
recv: b'ESTAS' de ('127.0.0.1', 56389)
```

En TCP el mismo envío dio **una sola** lectura (`b'HOLACOMOESTAS'`). La diferencia
es que la unidad de UDP es el datagrama y la de TCP es el byte.

### 2.2 El buffer chico trunca

Acá hay una diferencia de plataforma que vale la pena anotar:

```
=== Linux (WSL) ===
primer recvfrom: 10 bytes (trunco en silencio)
segundo recvfrom: nada

=== Windows ===
primer recvfrom: OSError 10040
  ...el búfer utilizado para recibir un datagrama es más pequeño que el datagrama
segundo recvfrom: nada
```

**3. ¿Cuántos bytes trajo cada uno?** El primero, 10 (en Linux); el segundo,
**nada** — dio timeout.

**4. ¿Dónde quedaron los 90 bytes restantes?** Se **descartaron**. El kernel
entregó el datagrama, el programa pidió sólo 10 bytes, y el resto se tiró. No
quedan en ningún buffer esperando: un datagrama se consume entero o no se consume.

La diferencia entre sistemas es sólo si avisan: Linux trunca en silencio (POSIX lo
permite), Windows lanza `WSAEMSGSIZE`. En los dos casos los 90 bytes están
perdidos. La versión de Windows es más amable, porque al menos el bug no pasa
desapercibido.

**5. ¿Y en TCP?** No se habrían perdido. TCP es un flujo: lo que no se lee queda
en el buffer de recepción del kernel y lo devuelve el `recv()` siguiente. Esa es
la diferencia de fondo — en TCP `recv(10)` sobre 100 bytes deja 90 pendientes; en
UDP los descarta.

**6. ¿Qué tamaño de buffer conviene?** **65535**, el máximo que puede tener un
datagrama UDP (el campo de longitud de la cabecera son 16 bits). Con ese tamaño
nunca se trunca nada. No hay razón para arriesgarse a perder datos por ahorrar
unos KB de buffer.

---

## Ejercicio 3: Protocolo confiable (OBLIGATORIO)

### Parte A: ver el problema

**3. La característica central de UDP, en una frase:** manda y se olvida — no
garantiza que el datagrama llegue, ni que llegue una sola vez, ni que llegue en
orden, y no avisa cuando se pierde.

**3b. Sobre el desorden:** sin `tc`, los "saltos hacia atrás" dan 0 porque
loopback entrega en orden. Con `tc netem reorder` dejan de dar 0. Para un
protocolo que asuma orden, eso es fatal: un mensaje que llega después que su
sucesor se interpreta como si fuera más nuevo, y el estado queda corrompido. Es
justamente por eso que la parte D necesita números de secuencia — sirven tanto
para detectar duplicados como para reordenar.

### Parte B: retransmisión

Con 30 % de pérdida simulada (aplicada en **los dos sentidos**, así que la
probabilidad de que una ida y vuelta completa funcione es 0,7 × 0,7 ≈ 49 %):

```
  uno      -> UNO          (2 intento/s)
  dos      -> DOS          (1 intento/s)
  tres     -> TRES         (1 intento/s)
  cuatro   -> CUATRO       (1 intento/s)
  cinco    -> CINCO        (4 intento/s)
  promedio de intentos: 1.8
  sin respuesta: 0/5
```

**4. Promedio: 1,8 intentos**, consistente con ~49 % de éxito por intento.

**5. Con 70 % de pérdida** la probabilidad de una ida y vuelta completa cae a
0,3 × 0,3 = **9 %**:

```
  promedio de intentos: 8.8
  sin respuesta: 4/5
```

**Sigue funcionando pero ya casi no sirve**: con 10 intentos sólo entra uno de
cinco mensajes. Es el punto donde conviene replantear si UDP es la herramienta
correcta (ver parte E).

**6. El timeout:**

- **Muy corto (0,01 s)**: reintenta antes de que la respuesta tenga tiempo de
  llegar. Multiplica el tráfico con duplicados inútiles y puede empeorar la
  congestión que causaba la pérdida — un bucle de retroalimentación clásico.
- **Muy largo (5 s)**: cada pérdida cuesta 5 segundos de espera. Confiable pero
  inusable.

Por eso los protocolos reales no usan un timeout fijo: lo **estiman** midiendo el
RTT y lo ajustan dinámicamente. TCP usa el algoritmo de Jacobson/Karels, que
promedia el RTT y su variación, y además duplica el timeout en cada reintento
(*exponential backoff*).

### Parte C: el problema del duplicado

**7. ¿Cómo sabe el cliente qué se perdió?** **No puede saberlo.** Desde su lado los
dos casos son idénticos: mandó algo y no recibió nada. No hay forma de distinguir
"se perdió mi pedido" (el servidor nunca lo vio) de "se perdió la respuesta" (el
servidor ya lo procesó). Esa ambigüedad es irreducible: es el problema de los dos
generales.

**8. Comprobado.** Con 30 % de pérdida, sin números de secuencia:

```
  mensajes distintos que mando el cliente: 5
  datagramas que recibio el servidor:      6
  veces que hizo el TRABAJO REAL:          6
  -> ejecuto 1 veces de mas
```

El servidor hizo el trabajo **6 veces para 5 mensajes**: un reintento llegó cuando
el pedido original ya se había procesado y lo volvió a procesar.

**9. ¿Por qué es grave con "transferir $100"?** Porque la operación no es
**idempotente**. Poner en mayúsculas dos veces da el mismo resultado; transferir
$100 dos veces mueve $200. El cliente creyó que su pedido se había perdido y
reintentó, y el servidor —que ya lo había ejecutado— lo ejecutó de nuevo. El
usuario pierde plata por un paquete perdido.

Es el mismo problema que reaparece en HTTP con `POST` y la idempotencia (clase
19), y la solución es la misma: una clave que identifique la operación para que el
servidor reconozca el reintento.

### Parte D: números de secuencia

```
  seq=0 uno      -> UNO          (2 intento/s)
  seq=1 dos      -> DOS          (3 intento/s)
  seq=2 tres     -> TRES         (1 intento/s)
  seq=3 cuatro   -> CUATRO       (1 intento/s)
  seq=4 cinco    -> CINCO        (2 intento/s)
  datagramas que recibio el servidor: 8
  veces que hizo el TRABAJO REAL:     5 (mensajes distintos: 5)
  -> OK: la deduplicacion evito el trabajo repetido
```

**10.** El servidor recibió **8 datagramas** pero hizo el trabajo **5 veces**, una
por mensaje distinto. Los 3 duplicados se contestaron con la respuesta guardada,
sin volver a ejecutar nada. Con 70 % de pérdida: 11 datagramas recibidos, **5**
trabajos. Exactamente lo que pide el enunciado.

**11. ¿Por qué el cliente tiene que descartar respuestas con `seq` distinto?**
Porque una respuesta demorada de un intento anterior puede llegar **después** de
que el cliente ya pasó al pedido siguiente. Sin el chequeo, el cliente tomaría la
respuesta vieja como respuesta del pedido nuevo y a partir de ahí todo queda
corrido un lugar — y lo peor es que no hay ningún error: los datos simplemente no
se corresponden.

Por eso en `cliente_con_seq()` el `recvfrom` está dentro de un bucle que compara
`rseq == seq` y descarta lo que no coincida.

**12. Comparado con `confiable.py`:** la estructura es la misma —prefijo de 4
bytes con `struct.pack('!I', ...)`, reintentos con timeout, diccionario de `seq`
vistos del lado del servidor. La métrica que importa es la misma que mide mi
ejercicio: la diferencia entre "datagramas recibidos" y "veces que hizo el
trabajo", que es lo que demuestra que la deduplicación funciona.

### Parte E: reflexión

**13. Tres garantías de TCP que esta implementación NO tiene:**

1. **Orden.** Los números de secuencia detectan duplicados, pero el cliente manda
   un mensaje y espera la respuesta antes del siguiente. Si hubiera varios en
   vuelo, nada reordena lo que llegue desordenado: haría falta un buffer de
   reensamblado.
2. **Control de flujo.** Nada impide saturar a un receptor lento. TCP tiene la
   ventana deslizante, que le permite al receptor decir cuánto puede aceptar; acá
   el emisor manda a la velocidad que quiere.
3. **Control de congestión.** Ante pérdidas, TCP *baja* la tasa de envío
   (slow start, congestion avoidance) porque la pérdida suele indicar una red
   saturada. Mi implementación hace lo contrario: reintenta igual de rápido, lo
   que empeora la congestión que causó la pérdida.

Se podrían agregar dos más: la conexión (handshake, saber que el otro está vivo) y
el cierre ordenado, que permite distinguir "terminó" de "se cayó".

**14. ¿Cuándo dejar de agregar confiabilidad y usar TCP?** Cuando se empieza a
necesitar **más de una** de esas garantías. Cada una por separado es un problema
acotado; juntas son TCP, y reimplementarlo peor no tiene sentido — TCP lleva 40
años de ajustes finos que un protocolo casero no va a igualar.

La regla práctica: UDP conviene cuando se necesita **algo que TCP no puede dar**,
no cuando se quiere ahorrar lo que TCP ya da. Los casos legítimos son:

- **Latencia por encima de integridad**: voz y video, donde retransmitir un
  paquete viejo es peor que perderlo.
- **Un pedido, una respuesta, sin estado**: DNS, donde establecer una conexión
  costaría más que el intercambio.
- **Multicast o broadcast**: TCP es punto a punto y no puede hacerlo.
- **Control total del comportamiento ante pérdida**: es lo que hace QUIC, que
  reimplementa confiabilidad sobre UDP para evitar el *head-of-line blocking* de
  TCP. Pero eso lo hacen equipos grandes con muy buenas razones.

### Checklist del obligatorio

- [x] Cliente que reintenta con timeout
- [x] Funciona con 70 % de pérdida simulada
- [x] Servidor que cuenta cuántas veces hace el trabajo real
- [x] Demostrar que sin deduplicación el servidor procesa de más (6 trabajos / 5 mensajes)
- [x] Números de secuencia con `struct.pack('!I', ...)`
- [x] Servidor que deduplica y reenvía la respuesta guardada (5 trabajos / 8 datagramas)
- [x] Cliente que descarta respuestas con `seq` incorrecto
- [x] Explicar tres garantías de TCP que faltan

---

## Ejercicio 4: `connect()` en UDP

```
=== Linux (WSL) ===
--- con connect() ---
  ConnectionRefusedError
--- sin connect(), con sendto/recvfrom ---
  timeout (nadie avisa nada)

=== Windows ===
--- con connect() ---
  ConnectionResetError
--- sin connect() ---
  ConnectionResetError
```

**1. ¿Qué excepción y de dónde sale?** En Linux, `ConnectionRefusedError`. La
información **no** viene de UDP: viene de **ICMP**. Cuando llega un datagrama a un
puerto donde nadie escucha, el kernel del destino responde un ICMP *port
unreachable*. Ese mensaje es de la capa de red, no de transporte, y por eso puede
existir aunque UDP no tenga conexiones.

**2. Sin `connect()`:** en Linux, **timeout**: el ICMP llega igual, pero el kernel
no sabe a qué socket entregárselo y lo descarta. (En Windows el error aparece en
los dos casos.)

**3. ¿Qué hace realmente `connect()` en UDP?** No manda ningún paquete ni establece
nada — no hay handshake. Lo único que hace es **guardar la dirección del destino
en el socket**, con tres consecuencias:

1. Se puede usar `send()`/`recv()` en vez de `sendto()`/`recvfrom()`.
2. El socket **sólo acepta datagramas de esa dirección**; los de cualquier otro
   remitente se descartan.
3. Y la que importa acá: al tener un destino asociado, el kernel puede **vincular
   los errores ICMP a ese socket** y reportarlos. Sin `connect()` no sabe a quién
   corresponden.

**4. ¿Y si otro host manda un datagrama?** Con `connect()` puesto, el kernel lo
**descarta** sin que el programa se entere. Es un filtro básico de remitente.

**5. ¿Por qué no depender de este mecanismo en Internet?** Porque el ICMP es poco
confiable como señal:

- Muchos **firewalls bloquean ICMP** por completo, así que el *port unreachable*
  nunca llega y el cliente se queda esperando el timeout igual.
- Es **best-effort**: el propio ICMP puede perderse, y nadie lo retransmite.
- Puede ser **falsificado**: un tercero que pueda inyectar paquetes puede mandar un
  ICMP falso para cortar la comunicación.
- El comportamiento **varía según el sistema**, como se ve arriba entre Linux y
  Windows.

O sea que la ausencia de error no prueba que el servidor esté vivo, y su presencia
no es confiable. El timeout sigue siendo obligatorio.

---

## Ejercicio 5: Broadcast

```
--- con SO_BROADCAST ---
[servidor] respondi a ('10.100.200.200', 49668)
[cliente] ('10.100.200.200', 8082) respondió: b'Compu-Fran05'
--- sin SO_BROADCAST ---
[cliente] PermissionError: [WinError 10013] Intento de acceso a un socket
          no permitido por sus permisos de acceso
```

**1. ¿Qué error da sin `setsockopt`?** `PermissionError` (WinError 10013 en
Windows, `EACCES` en Linux). La protección existe porque un broadcast **molesta a
toda la red**: obliga a cada máquina del segmento a procesar el paquete, aunque no
le interese. Exigir que el programa lo pida explícitamente evita que alguien
inunde la red por accidente, con un `sendto` mal escrito.

**2. El servidor** está en `ejercicio5.py`: escucha en `('', 8082)` —todas las
interfaces, necesario para recibir broadcast— y responde al `DISCOVER?` con
`socket.gethostname()`. Probado: respondió `b'Compu-Fran05'`.

**3 y 4. ¿Funciona entre redes distintas?** No: **los routers no reenvían
broadcast**. Si lo hicieran, un solo paquete a `255.255.255.255` se propagaría por
toda Internet multiplicándose en cada router — una tormenta de broadcast que
tumbaría la red. Por eso el broadcast se detiene en el límite del dominio de
difusión, o sea la red local.

**5. ¿Por qué DHCP no podría usar TCP?** Porque TCP necesita que las dos puntas
tengan dirección IP para abrir una conexión, y una máquina que arranca **todavía
no tiene IP**: es justamente lo que le va a pedir al servidor DHCP. Tampoco conoce
la dirección del servidor.

Con UDP sí puede: manda un `DHCPDISCOVER` desde `0.0.0.0` hacia
`255.255.255.255`, sin conocer a nadie y sin tener identidad. Es un caso donde
UDP no es una optimización sino la única opción posible — el broadcast y la
ausencia de conexión son requisitos, no concesiones.

---

## Ejercicio 6: Fragmentación y MTU

**1. MTU real** (`ip link show`):

```
mtu 1472     (eth0, la interfaz de WSL)
mtu 65536    (lo, loopback)
```

La de `eth0` es 1472 y no los 1500 típicos de Ethernet, porque WSL2 va por una
red virtual con encapsulamiento que se come 28 bytes. El loopback usa 65536
porque nunca sale de la máquina: no hay límite físico que respetar.

**2. Payload UDP sin fragmentar:** restando 20 de cabecera IP y 8 de UDP:

- con MTU 1500 → **1472 bytes**
- con MTU 1472 (esta máquina) → **1444 bytes**

**3. ¿Llega un datagrama de 60000 bytes?** Sí, probado contra un servidor local:

```
   60000 bytes: enviados 20, recibidos 20, completos 20
    1000 bytes: enviados 20, recibidos 20, completos 20
```

Los 20 llegaron completos en los dos tamaños. Pero esto es **loopback**, donde la
MTU es 65536 y no se pierde nada: no hay fragmentación ni pérdida que medir. Para
los puntos 4 y 5 haría falta `tc netem`, que necesita root.

**5. El cálculo, que es lo que importa.** Con MTU 1500, un datagrama de 60000
bytes se parte en **41 fragmentos IP**. La regla clave es que **IP no retransmite
fragmentos**: si se pierde **uno solo**, el receptor no puede reensamblar y
descarta **el datagrama entero**.

Con 5 % de pérdida por paquete:

- **Datagrama de 1000 bytes** (1 fragmento): llega con probabilidad 0,95 →
  **5 % de pérdida**.
- **Datagrama de 60000 bytes** (41 fragmentos): llega sólo si llegan los 41, o sea
  0,95⁴¹ ≈ **0,12** → **88 % de pérdida**.

La pérdida efectiva pasa de 5 % a 88 %: no se multiplica por 41, crece
*exponencialmente* con la cantidad de fragmentos. Esa es la razón por la que los
protocolos reales sobre UDP mantienen sus datagramas por debajo de la MTU —DNS usa
512 bytes, QUIC ronda 1200— y prefieren partir el mensaje a nivel de aplicación,
donde cada trozo se puede retransmitir por separado.
