# Clase 13: Sockets TCP — Ejercicios

Resolución de los ejercicios de la clase 13. Cada archivo es ejecutable y lleva
las respuestas conceptuales en un bloque de texto al final, siguiendo el estilo
del resto del repositorio.

Todos los ejercicios **corren solos**, sin necesitar dos terminales ni `netcat`
(que no viene en Windows): cada uno levanta su propio servidor en un hilo.
Igual, los que tienen sentido probar a mano aceptan un flag `--servidor` para
usarlos contra `nc`.

```bash
python ejercicio3.py
```

## Índice

| Archivo | Tema | Cómo se corre |
|---|---|---|
| [ejercicio1.py](ejercicio1.py) | Primer contacto: cliente, servidor, `SO_REUSEADDR` | `python ejercicio1.py` |
| [ejercicio2.py](ejercicio2.py) | Entender `recv()`, la señal de cierre, `send()` vs `sendall()` | `python ejercicio2.py` |
| [ejercicio3.py](ejercicio3.py) | **Framing (obligatorio)**: delimitador y longitud | `python ejercicio3.py` |
| [ejercicio4.py](ejercicio4.py) | Bytes y encoding: el carácter UTF-8 partido | `python ejercicio4.py` |
| [ejercicio5.py](ejercicio5.py) | Errores, reintentos con backoff y timeouts | `python ejercicio5.py` |
| [ejercicio6.py](ejercicio6.py) | El límite del servidor secuencial (prepara la clase 14) | `python ejercicio6.py` |

Modos con dos terminales, para los que se quieran probar a mano:

```bash
python ejercicio1.py --servidor --loop
```

```bash
python ejercicio3.py --servidor-lineas
```

```bash
python ejercicio6.py --servidor --backlog 1
```

---

## Verificación del ejercicio obligatorio (framing)

`python ejercicio3.py` corre las pruebas y termina imprimiendo el checklist:

- [x] Framing por delimitador funcionando
- [x] Framing por longitud funcionando
- [x] Ambos sobreviven a recibir todos los mensajes en un solo `sendall()`
- [x] Ambos sobreviven a recibir un mensaje byte por byte
- [x] `recibir_exacto()` implementado con bucle, no con un solo `recv()`
- [x] El framing por longitud maneja contenido con `\n` adentro
- [x] Manejo correcto del cierre de conexión (`recv()` devuelve `b''`)

### Parte D — la tabla comparativa

|  | Delimitador | Longitud |
|---|---|---|
| **Contenido binario arbitrario** | No directo: hay que escapar el delimitador, o prohibirlo | Sí, directo: el contenido nunca se inspecciona |
| **Depurable con `nc`** | Sí: es texto plano, se escribe y se lee a mano | No: la cabecera son 4 bytes binarios |
| **Hay que saber el tamaño antes** | No: se puede ir mandando a medida que se genera | Sí, obligatorio antes del primer byte del cuerpo |

En una línea: **delimitador** para protocolos de texto (HTTP, SMTP, IRC, Redis);
**longitud** para binario o mensajes grandes (gRPC, WebSocket, TLS).

HTTP combina las dos porque cada mitad del mensaje tiene un problema distinto:
los headers son texto de cantidad desconocida y conviene que sean legibles, así
que van con delimitador; el cuerpo puede ser un JPEG y además interesa saber su
tamaño de antemano para reusar la conexión, así que va con `Content-Length`.
Y cuando el servidor genera el cuerpo sobre la marcha y tampoco sabe el tamaño,
usa `Transfer-Encoding: chunked`, que es framing por longitud aplicado a cada
trozo. El detalle está desarrollado al final de [ejercicio3.py](ejercicio3.py) y
verificado contra un servidor real en
[adicional3_cliente_http.py](adicional3_cliente_http.py).

---

## Resultados medidos en esta máquina

Algunas respuestas dependen del sistema operativo. Todo esto se midió corriendo
los ejercicios en **Windows 11, Python 3.13**, y está anotado en el archivo
correspondiente, con la aclaración de qué pasaría en Linux.

**Los tres `sendall()` del ejercicio 3, parte A.** No se fusionan siempre: con
el servidor esperando en `recv()` salieron tres lecturas separadas, y con el
servidor ocupado medio segundo salieron fusionadas en una. Mismo código de
cliente, distinto resultado. Por eso `ejercicio3.py --parte-a` muestra los dos
escenarios en vez de asumir uno: el emisor no controla cómo se agrupan sus
bytes del otro lado.

**`send()` de 10 MB (ejercicio 2, punto 8).** En Windows sobre loopback devuelve
los 10.485.760 bytes completos, y sigue haciéndolo aunque se ponga `SO_SNDBUF`
en 8192, el receptor no lea nunca, el socket sea no bloqueante y el payload suba
a 100 MB. Winsock además define que un `send()` bloqueante no retorna hasta
copiar todo. En Linux la misma llamada devuelve una fracción. La conclusión no
cambia, y de hecho es peor: el comportamiento depende del sistema operativo, así
que código que anda perfecto acá manda mensajes truncados al desplegarlo en un
servidor Linux. Por eso la regla es `sendall()`, no "probalo y fijate".

**`ConnectionRefusedError` (ejercicio 5, punto 1).** Tarda 2,03–2,05 s de forma
consistente, no milisegundos: Windows reintenta el SYN antes de dar por buena la
negativa. En Linux es instantáneo. Por eso `conectar_con_reintentos()` usa
`timeout=5` y no `2`: con 2 saltaría `TimeoutError` antes de que aparezca el
error real, y el diagnóstico quedaría equivocado.

**Backlog lleno (ejercicio 6, punto 5).** Con `--backlog 1` y cuatro clientes,
el cuarto recibe `ConnectionRefusedError` y el tercero queda en `SYN_SENT`
reintentando. Linux, en cambio, descarta el SYN en silencio y el cliente sólo
percibe lentitud inexplicable.

**El ejercicio 4 se moría al imprimir.** La consola de Windows usa cp1252 y no
puede mostrar `€` ni emoji: el ejercicio sobre encoding fallaba con
`UnicodeEncodeError` al escribir en pantalla. Es el mismo problema de fondo
—texto contra bytes— pero del lado de la salida estándar en vez del socket. Se
resuelve con `sys.stdout.reconfigure(encoding='utf-8')` al principio del archivo.

---

*Computación II - 2026 - Clase 13*
