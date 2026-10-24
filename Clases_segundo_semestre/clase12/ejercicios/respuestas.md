# Clase 12: Redes — Respuestas

Todo corrido en **WSL (Ubuntu) sobre Windows 11**. Eso importa para varias
respuestas: WSL2 tiene su propia pila de red detrás de NAT, así que la IP que se
ve no es la de la red wifi real.

`dig`, `tcpdump` y `traceroute` no están instalados en esta máquina. Donde hizo
falta usé lo que sí hay (`resolvectl`, `ss`, Python) y lo aclaro en cada punto.

---

## Ejercicio 1: Reconocimiento de la propia máquina

### 1.1 Interfaces y direcciones

```
$ ip -brief addr show
lo      UNKNOWN  127.0.0.1/8 10.255.255.254/32 ::1/128
eth0    UP       172.27.178.163/20 fe80::215:5dff:fe2c:1c6f/64
```

**1. ¿Cuántas interfaces? ¿Cuál es loopback?** Dos: `lo` y `eth0`. La de loopback
es `lo`, con `127.0.0.1/8` en IPv4 y `::1/128` en IPv6. Es virtual: no existe
hardware detrás, y el tráfico que entra por ahí nunca sale de la máquina.

**2. ¿Es privada la IP local?** `172.27.178.163` sí es privada: cae en el bloque
`172.16.0.0/12`, que abarca de `172.16.x.x` a `172.31.x.x`. Las tres familias
privadas (RFC 1918) son `10.0.0.0/8`, `172.16.0.0/12` y `192.168.0.0/16`, y no se
rutean en Internet.

Detalle de WSL: esta IP **no** es la de la red wifi, es la de la red virtual que
Windows arma para WSL2. La máquina Windows tiene otra IP en la LAN real.

**3. ¿Hay IPv6? ¿Empieza con `fe80:`?** Sí: `fe80::215:5dff:fe2c:1c6f/64`. El
prefijo `fe80::/10` es link-local, o sea que sólo vale dentro del segmento físico
y no se rutea. Se autoconfigura sola, sin DHCP. Para salir a Internet por IPv6
haría falta además una dirección global.

### 1.2 Rutas

```
$ ip route
default via 172.27.176.1 dev eth0 proto kernel
172.27.176.0/20 dev eth0 proto kernel scope link src 172.27.178.163
```

**4. Gateway por defecto:** `172.27.176.1`, alcanzable por `eth0`. La línea
`default` es el comodín: todo lo que no matchee una ruta más específica se manda
ahí.

**5. Relación con la propia IP:** las dos están en la misma red,
`172.27.176.0/20`. La máscara `/20` fija los primeros 20 bits, así que la red va
de `172.27.176.0` a `172.27.191.255`, y tanto `172.27.178.163` como
`172.27.176.1` caen adentro. Eso es lo que permite que la máquina le hable al
gateway directamente, sin intermediarios: está en su mismo segmento.

Y de ahí sale la decisión que toma el sistema por cada paquete: si el destino
está en la red local, lo manda directo (resolviendo la MAC con ARP); si no, se lo
entrega al gateway.

### 1.3 Puertos en escucha

```
$ ss -tln
State  Recv-Q Send-Q  Local Address:Port
LISTEN 0      1000   10.255.255.254:53
LISTEN 0      4096       127.0.0.54:53
LISTEN 0      4096    127.0.0.53%lo:53
```

**6. Tres servicios:** los tres son `systemd-resolved`, el resolver de DNS local,
escuchando en el puerto 53 en tres direcciones distintas. Esta es una instalación
de WSL bastante pelada; en una máquina de escritorio aparecerían además `:22`
(ssh), `:631` (cups), etc. Corrí `ss -tln` sin `-p` porque mostrar el proceso
dueño de cada socket requiere root.

**7. ¿Cuáles en 127.0.0.1 y cuáles en 0.0.0.0?** Acá ninguno escucha en
`0.0.0.0`: los tres están atados a direcciones concretas, dos de ellas de
loopback. La diferencia es la que importa para la seguridad:

- Atado a `127.0.0.1` → sólo alcanzable desde la propia máquina. El kernel
  descarta cualquier paquete que llegue por otra interfaz.
- Atado a `0.0.0.0` (o `*`) → acepta por **todas** las interfaces, así que
  cualquiera en la misma red wifi puede conectarse.

Por eso un servidor de desarrollo conviene que escuche en `127.0.0.1`: sin
autenticación ni TLS, atarlo a `0.0.0.0` lo deja expuesto a toda la red.

---

## Ejercicio 2: Resolución de nombres

`dig` no está instalado, así que usé `resolvectl query`, que consulta el mismo
`systemd-resolved`.

```
$ resolvectl query google.com
google.com: 172.217.28.14
            2800:3f0:4002:808::200e
-- Information acquired via protocol DNS in 37.9ms.
-- Data from: network
```

**1. Dirección:** `172.217.28.14` en IPv4, y también devolvió una IPv6
(`2800:3f0:4002:808::200e`). Es un nombre dual-stack.

**2 y 3. TTL y cache:** `resolvectl` no muestra el TTL (ahí `dig` sería mejor),
pero el efecto del cacheo se ve igual de claro en el tiempo. Segunda consulta
inmediata:

```
-- Information acquired via protocol DNS in 813us.
-- Data from: cache
```

De **37,9 ms a 813 µs**, unas 46 veces más rápido, y el propio comando dice
`Data from: cache`. El TTL es justamente el que gobierna esto: es la cantidad de
segundos que un resolver tiene permitido guardar la respuesta antes de volver a
preguntar. Al repetir la consulta el TTL que informaría `dig` aparece **más
bajo**, porque va descontando el tiempo que la entrada lleva en cache.

Quien cachea acá es `systemd-resolved`, el resolver local de la máquina. Más
arriba también cachean el resolver del ISP y los servidores intermedios.

**4. Varias direcciones:** un nombre grande devuelve varias por dos razones:
reparto de carga (cada cliente toma una distinta) y tolerancia a fallos (si una
no responde, el cliente prueba la siguiente). Es también lo que hacen los CDN,
devolviendo direcciones distintas según desde dónde se pregunte.

---

## Ejercicio 3: Cliente y servidor con netcat

**1. ¿Qué pasa al cerrar cada lado?** Si se corta el cliente con Ctrl+C, el
servidor ve el fin de la entrada y termina también: `nc` cierra cuando recibe el
FIN. Si se corta el servidor, el cliente ve lo mismo del otro lado. En los dos
casos el cierre es ordenado (FIN), no un error.

**2. La cuádrupla.** Lo que identifica una conexión TCP son cuatro valores: IP
origen, puerto origen, IP destino, puerto destino. En una conexión por loopback
al 8080 serían `127.0.0.1:<puerto efímero>` ↔ `127.0.0.1:8080`. El socket que
escucha sólo tiene definida la mitad local (`0.0.0.0:8080`), por eso puede
compartirse entre todas las conexiones entrantes.

**3. Dos clientes a la vez.** Lo probé: el primer cliente mandó `cliente-1` y se
quedó conectado; mientras tanto arranqué el segundo.

```
  cliente-2 salio con codigo 124     (124 = seguia esperando, no fue rechazado)
  servidor recibio:
    cliente-1
```

El segundo cliente **conecta** (el `connect()` tiene éxito, el kernel completa el
handshake y lo deja en la cola de `listen()`), pero `nc -l` atiende una sola
conexión: nunca llama a `accept()` de nuevo, así que lo que manda el segundo
queda sin leer. Es exactamente el problema del servidor secuencial que se
desarrolla en la clase 13, y la confusión típica: "conectó" no significa "lo
están atendiendo".

**4. Puerto ocupado.** Con un servidor ya escuchando en 8080, intentar atar otro
da:

```
OSError: [Errno 98] Address already in use
```

(Lo verifiqué en Python para ver el mensaje exacto; con `nc` el resultado en mi
corrida fue inconsistente.) Ese error reaparece en la clase 13, donde se resuelve
con `SO_REUSEADDR` para el caso de `TIME_WAIT`.

**5. Por qué un servidor de desarrollo escucha en 127.0.0.1:** porque así sólo se
puede acceder desde la propia máquina, y un servicio de desarrollo normalmente no
tiene autenticación, ni HTTPS, ni límites de tasa — exponerlo a toda la red wifi
sería regalar acceso a la base de datos de prueba y a cualquier endpoint de debug.

---

## Ejercicio 4: HTTP a mano

```
$ printf 'GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n' \
    | nc example.com 80
HTTP/1.1 200 OK
Date: Tue, 06 Oct 2026 12:06:25 GMT
Content-Type: text/html; charset=utf-8
Transfer-Encoding: chunked
Connection: close
Server: cloudflare
Last-Modified: Sun, 04 Oct 2026 20:44:03 GMT
Age: 9492
cf-cache-status: HIT
```

**1. Código de estado:** `200 OK`. Familia 2xx, éxito.

**2. Tres headers:**

- `Content-Type: text/html; charset=utf-8` — qué tipo de contenido viene y en qué
  codificación hay que decodificarlo.
- `Transfer-Encoding: chunked` — el cuerpo viene en trozos, cada uno precedido por
  su tamaño en hexadecimal. Se usa cuando el servidor no sabe el tamaño total de
  antemano, y reemplaza a `Content-Length`.
- `Connection: close` — el servidor va a cerrar la conexión al terminar, que es lo
  que pedimos nosotros en la petición.

**3. Sin el header `Host`:**

```
HTTP/1.1 400 Bad Request
Server: cloudflare
```

HTTP/1.1 lo exige porque muchos sitios comparten una misma IP (*virtual
hosting*): el servidor necesita saber a cuál de todos se le está hablando. En
HTTP/1.0 no existía, y por eso cada sitio necesitaba su propia dirección IP — una
de las razones del agotamiento de IPv4.

**4. `GET /noexiste`:**

```
HTTP/1.1 404 Not Found
```

**5. Con `\n` en vez de `\r\n`:** funcionó, devolvió `200 OK`. Pero el RFC exige
`\r\n` (CRLF) como terminador de línea, así que esto es tolerancia del servidor,
no algo garantizado. Depender de eso es mala idea porque el código anda contra un
servidor y falla contra otro, y el fallo aparece recién en producción o al cambiar
de proveedor. Es el principio de robustez llevado al lado equivocado: ser
tolerante al recibir está bien, ser descuidado al emitir no.

---

## Ejercicio 5: Observar el handshake

`tcpdump` no está instalado y además necesita root, así que va el diagrama
esperado en vez de la captura:

```
cliente                           servidor
   |                                  |
   |------- SYN         [S]  -------->|   "quiero conectarme", seq=x
   |<------ SYN-ACK     [S.] ---------|   "aceptado", seq=y, ack=x+1
   |------- ACK         [.]  -------->|   "confirmado", ack=y+1
   |         (conexión establecida)   |
   |------- PSH-ACK "test\n" [P.] --->|   los 5 bytes de datos
   |<------ ACK         [.]  ---------|   confirmación
   |------- FIN-ACK     [F.] -------->|   "no mando más"
   |<------ ACK         [.]  ---------|
   |<------ FIN-ACK     [F.] ---------|   el otro lado también cierra
   |------- ACK         [.]  -------->|
```

**2. Cuántos paquetes para mandar "test":** el handshake son 3, los datos con su
confirmación 2, y el cierre 4. Unos **9 paquetes para 5 bytes de datos**. Con
cabeceras de 20 bytes de IP + 20 de TCP, son unos 360 bytes de sobrecarga para
transportar 5. Esa desproporción es la razón de ser de `keep-alive` en HTTP y del
algoritmo de Nagle: establecer una conexión TCP es caro, y conviene reutilizarla.

**3. El cierre:** aparece `[F]` (FIN) de cada lado, cada uno con su ACK. Son
cuatro paquetes porque TCP cierra cada dirección por separado: un lado puede
dejar de mandar y seguir recibiendo (es el `shutdown(SHUT_WR)` de la clase 13).

---

## Ejercicio 6: TCP es un flujo (OBLIGATORIO)

### Parte A: el problema

Usé un receptor en Python en vez de `nc | od -c`, porque `od` acumula toda la
entrada y no deja ver cuántas lecturas hubo — que es justamente lo que se quiere
medir.

**1. Tres `send()` seguidos, sin pausa:**

```
  recv #1: b'HOLACOMOESTAS'
  total recv con datos: 1
```

Los tres envíos llegaron fusionados en **una sola** lectura. No se distinguen:
el receptor no tiene forma de saber dónde terminaba uno y empezaba el otro.

**2. Con `time.sleep(1)` entre envíos:**

```
  recv #1: b'HOLA'
  recv #2: b'COMO'
  recv #3: b'ESTAS'
  total recv con datos: 3
```

Ahora sí salieron separados. **Pero no se puede confiar en eso.** Lo único que
cambió es que entre envío y envío el receptor tuvo tiempo de vaciar el buffer, así
que cada `recv()` encontró un solo mensaje. Es una coincidencia de temporización,
no una garantía: basta que el receptor esté ocupado un instante, o que la red
demore un paquete, para que vuelvan a juntarse. Un `sleep` no es un protocolo.

### Parte B: la pregunta

**3. ¿Es un bug de TCP?** No. TCP promete tres cosas —que los bytes lleguen, sin
errores y **en orden**— y nunca prometió conservar los límites de cada envío. Para
TCP no existen los mensajes: es un flujo de bytes (`SOCK_STREAM`). Agrupar envíos
es además deseable, porque mandar un paquete de 40 bytes de cabecera por cada 4 de
datos sería un desperdicio; es lo que hace el algoritmo de Nagle.

Si la aplicación necesita mensajes, los tiene que construir ella. Eso es el
*framing*, y es el tema central de la clase 13.

**4. Dos formas de delimitar:**

| Esquema | Cómo funciona | Si el mensaje contiene el delimitador |
|---|---|---|
| **Delimitador** | Marcar el fin con un byte que no aparezca en el contenido, típicamente `\n` | Se rompe: el receptor parte el mensaje en dos. Hay que escapar el delimitador al enviar y desescaparlo al recibir, o prohibirlo |
| **Prefijo de longitud** | Mandar primero el tamaño en un formato fijo (ej. 4 bytes big-endian) y después el contenido | No hay problema: el contenido nunca se inspecciona, se leen exactamente N bytes. Sirve para binario arbitrario |

### Parte C: UDP para contrastar

```
$ python3 udp_srv.py
Esperando datagramas en localhost:8080 (timeout 5s)...
recv: b'HOLA' de ('127.0.0.1', 56389)
recv: b'COMO' de ('127.0.0.1', 56389)
recv: b'ESTAS' de ('127.0.0.1', 56389)
(timeout, fin)
```

**5. Tres `recvfrom`**, uno por cada `sendto`, sin pausas de por medio y sin
ninguna precaución especial. En TCP el mismo envío dio **una sola** lectura.

**6. Por qué UDP preserva los límites:** porque la unidad de UDP es el
**datagrama**, no el byte. Cada `sendto()` produce un paquete independiente que
viaja entero y se entrega entero: `recvfrom()` devuelve exactamente un datagrama,
ni más ni menos. TCP, en cambio, numera **bytes**, no mensajes, y es libre de
reagrupar como le convenga.

Es el intercambio de siempre: UDP conserva los límites pero no garantiza entrega
ni orden ni unicidad; TCP garantiza las tres cosas pero disuelve los límites.

**7. Por qué UDP no necesita `listen()` ni `accept()`:** porque no hay conexión
que establecer. `listen()` pone al socket en modo pasivo y `accept()` saca una
conexión ya establecida de la cola — las dos cosas presuponen un estado de
conexión que UDP no tiene. Un socket UDP con `bind()` ya puede recibir de
cualquiera, y `recvfrom()` devuelve la dirección del remitente en cada datagrama.
De ahí que un solo socket atienda a todos los clientes, mientras que en TCP hace
falta un socket por conexión.

### Checklist del obligatorio

- [x] Mostrar una corrida donde los tres envíos llegan agrupados
- [x] Explicar por qué eso no viola el contrato de TCP
- [x] Explicar por qué agregar `sleep` no es una solución
- [x] Proponer dos esquemas de delimitación y sus problemas
- [x] Mostrar que UDP preserva los límites
- [x] Explicar a qué se debe la diferencia

---

## Ejercicio 7: Puertos efímeros

```
$ cat /proc/sys/net/ipv4/ip_local_port_range
32768	60999
```

**1. El rango:** 32768 a 60999, o sea **28.231 puertos**. IANA recomienda
49152-65535 (16.384 puertos), así que no coinciden: Linux usa un rango propio,
más amplio y que arranca mucho antes.

La razón es histórica y práctica: el rango de IANA es una *recomendación*, no una
imposición, y Linux prioriza tener más puertos disponibles. Arrancar en 32768 casi
duplica la cantidad de conexiones salientes simultáneas. El costo es que el rango
pisa puertos registrados de servicios poco comunes, y por eso a veces un servicio
que quiere atarse a un puerto fijo en esa zona se encuentra con que un cliente se
lo tomó antes. Se ajusta escribiendo en ese mismo archivo.

**2. Puertos de origen asignados:**

```
('172.27.178.163', 55402)
('172.27.178.163', 60044)
('172.27.178.163', 55412)
('172.27.178.163', 37908)
('172.27.178.163', 40900)
```

Todos dentro del rango 32768-60999. **No siguen ningún patrón**: no son
consecutivos ni crecientes. Linux los elige con un algoritmo aleatorizado, a
propósito, porque puertos de origen predecibles facilitan ataques de falsificación
de paquetes.

**3. La tupla de `getsockname()`:** en esta máquina salió **IPv4**, así que la
tupla tiene **dos** elementos `(ip, puerto)`. Si la conexión hubiera salido por
IPv6 tendría **cuatro**: `(ip, puerto, flowinfo, scope_id)`. Por eso el código que
hace `host, puerto = sock.getsockname()` se rompe con IPv6, y hay que escribir
`sock.getsockname()[:2]` para que ande con las dos familias.

**4. Cuádruplas únicas:** con las conexiones abiertas, `ss -tn state established`
muestra una línea por conexión, todas hacia el mismo destino pero cada una con su
puerto de origen distinto. Eso es lo que las hace únicas: comparten tres de los
cuatro valores y se diferencian sólo en el cuarto.

**5. El techo de conexiones:**

- **Hacia el mismo servidor y puerto**: unas **28.231**, el tamaño del rango
  efímero. Los otros tres valores de la cuádrupla están fijos (mi IP, la IP del
  servidor, el puerto del servidor), así que lo único que puede variar es el
  puerto de origen, y cuando se agotan no se pueden abrir más.
- **Hacia servidores distintos**: el límite prácticamente desaparece, porque al
  cambiar la IP o el puerto de destino cambia la cuádrupla y el mismo puerto de
  origen se puede reutilizar. Ahí el techo pasa a ser otro: `ulimit -n`, la
  memoria, o las tablas de conexiones del kernel.

Por eso un balanceador de carga se queda sin puertos: habla todo el tiempo contra
el mismo puñado de servidores backend en el mismo puerto, que es justamente el
caso acotado. Se mitiga dándole varias IP de salida, ampliando el rango efímero, o
reutilizando conexiones con *keep-alive* en vez de abrir una por pedido.
