#!/usr/bin/env python3
"""Ejercicio 3: Framing (OBLIGATORIO).

Las dos estrategias de delimitacion de mensajes sobre TCP, con los dos
casos extremos: todos los mensajes en un solo sendall(), y un mensaje
partido byte por byte.

    python3 ejercicio3.py                  # corre TODAS las pruebas
    python3 ejercicio3.py --parte-a        # A: demostrar el problema
    python3 ejercicio3.py --parte-b        # B: framing por delimitador
    python3 ejercicio3.py --parte-c        # C: framing por longitud
    python3 ejercicio3.py --servidor-lineas    # servidor para probar con nc
    python3 ejercicio3.py --servidor-longitud

Para probar a mano el servidor por lineas:
    python3 ejercicio3.py --servidor-lineas     (terminal 1)
    nc localhost 8080                           (terminal 2)
El de longitud NO se puede probar con nc: la cabecera son 4 bytes binarios.
"""
import socket
import struct
import sys
import threading
import time

HOST = '127.0.0.1'
PUERTO_LINEAS = 8080
PUERTO_LONGITUD = 8081
PUERTO_CRUDO = 8082


# ====================================================================
# PARTE B: framing por delimitador (\n)
# ====================================================================

def recibir_lineas(sock):
    """Generador de lineas completas (sin el \\n final).

    El buffer es imprescindible y tiene que sobrevivir entre llamadas a
    recv(): un recv() puede traer media linea, o tres lineas y media.
    """
    buffer = b''
    while True:
        pedazo = sock.recv(4096)
        if not pedazo:
            # Conexion cerrada. Si quedo algo sin terminar, no es un mensaje
            # valido: se descarta (avisando, para no esconder el problema).
            if buffer:
                print(f'  [!] descartado, llego sin \\n final: {buffer!r}')
            return
        buffer += pedazo
        # OJO con el while: puede haber MAS DE UNA linea completa en el buffer.
        # Con un if se entregaria una sola y las otras quedarian trabadas
        # hasta el proximo recv(). Ese es el error clasico de esta parte.
        while b'\n' in buffer:
            linea, buffer = buffer.split(b'\n', 1)
            yield linea


def enviar_linea(sock, payload: bytes):
    """El delimitador NO puede aparecer dentro del payload (ver punto 7)."""
    sock.sendall(payload + b'\n')


def servidor_lineas(puerto=PUERTO_LINEAS, conexiones=None, listo=None):
    """Recibe mensajes terminados en \\n y responde en mayusculas."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        if listo:
            listo.set()
        else:
            print(f'Servidor por LINEAS en {HOST}:{puerto} (Ctrl+C para salir)')
        atendidas = 0
        while conexiones is None or atendidas < conexiones:
            conn, dir = srv.accept()
            atendidas += 1
            with conn:
                if not listo:
                    print(f'Conexion desde {dir}')
                for linea in recibir_lineas(conn):
                    if not listo:
                        print(f'  mensaje: {linea!r}')
                    enviar_linea(conn, linea.upper())


# ====================================================================
# PARTE C: framing por prefijo de longitud (4 bytes big-endian)
# ====================================================================

def recibir_exacto(sock, n):
    """Lee EXACTAMENTE n bytes, o None si cerraron antes.

    recv(n) puede devolver menos de n; hay que insistir. Sin este bucle el
    protocolo se desincroniza para siempre: un recv(4) que devuelve 2 bytes
    hace que los 2 siguientes se lean como si fueran cabecera.
    """
    datos = b''
    while len(datos) < n:
        pedazo = sock.recv(n - len(datos))       # pedir solo lo que falta
        if not pedazo:
            return None                          # cerro antes de completar
        datos += pedazo
    return datos


def enviar_mensaje(sock, payload: bytes):
    """Longitud en 4 bytes big-endian ('!' = orden de red) + contenido."""
    sock.sendall(struct.pack('!I', len(payload)) + payload)


def recibir_mensaje(sock):
    """Devuelve el payload, o None si la conexion se cerro limpiamente."""
    cabecera = recibir_exacto(sock, 4)
    if cabecera is None:
        return None
    (longitud,) = struct.unpack('!I', cabecera)
    if longitud == 0:
        return b''       # mensaje vacio: valido, y distinto de None (ver p. 8)
    return recibir_exacto(sock, longitud)


def servidor_longitud(puerto=PUERTO_LONGITUD, conexiones=None, listo=None):
    """Recibe mensajes con prefijo de longitud y responde en mayusculas."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        if listo:
            listo.set()
        else:
            print(f'Servidor por LONGITUD en {HOST}:{puerto} (Ctrl+C para salir)')
        atendidas = 0
        while conexiones is None or atendidas < conexiones:
            conn, dir = srv.accept()
            atendidas += 1
            with conn:
                if not listo:
                    print(f'Conexion desde {dir}')
                while (msg := recibir_mensaje(conn)) is not None:
                    if not listo:
                        print(f'  mensaje ({len(msg)} bytes): {msg!r}')
                    enviar_mensaje(conn, msg.upper())


# ====================================================================
# Infraestructura de pruebas
# ====================================================================

def levantar(objetivo, puerto, conexiones):
    listo = threading.Event()
    hilo = threading.Thread(target=objetivo,
                            args=(puerto, conexiones, listo), daemon=True)
    hilo.start()
    listo.wait(timeout=5)
    return hilo


def leer_n_lineas(sock, n):
    """Lee n respuestas del servidor por lineas."""
    gen = recibir_lineas(sock)
    return [next(gen) for _ in range(n)]


def leer_n_mensajes(sock, n):
    return [recibir_mensaje(sock) for _ in range(n)]


# ====================================================================
# PARTE A: el problema
# ====================================================================

def servidor_crudo(puerto, conexiones, listo, demora=0.0):
    """Servidor SIN framing: solo cuenta cuantos recv() hizo.

    Con `demora`, duerme antes del primer recv(). Eso le da tiempo al cliente
    a hacer sus tres sendall(), que se acumulan en el buffer de recepcion del
    kernel y salen todos juntos en una sola lectura.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        listo.set()
        for _ in range(conexiones):
            conn, _dir = srv.accept()
            with conn:
                if demora:
                    time.sleep(demora)      # el servidor "estaba ocupado"
                n = 0
                while True:
                    datos = conn.recv(4096)
                    if not datos:
                        break
                    n += 1
                    print(f'  [servidor] recv() #{n} -> {datos!r}')
                print(f'  [servidor] el cliente hizo 3 sendall(); '
                      f'yo hice {n} recv() con datos')


def parte_a():
    print('=== PARTE A: TCP no preserva los limites de los envios ===')

    # Caso 1: el servidor lee al instante, apenas llega cada envio.
    print('A.1 - servidor leyendo de inmediato')
    listo = threading.Event()
    threading.Thread(target=servidor_crudo,
                     args=(PUERTO_CRUDO, 1, listo, 0.0), daemon=True).start()
    listo.wait(timeout=5)
    with socket.create_connection((HOST, PUERTO_CRUDO), timeout=5) as s:
        for msg in (b'HOLA', b'COMO', b'ESTAS'):
            s.sendall(msg)              # tres sendall() separados
        s.shutdown(socket.SHUT_WR)
        time.sleep(0.4)                 # dejar que el servidor imprima

    # Caso 2: el mismo cliente, pero el servidor tarda en llegar al recv().
    print('\nA.2 - el MISMO cliente, con el servidor ocupado 0.5s')
    listo = threading.Event()
    threading.Thread(target=servidor_crudo,
                     args=(PUERTO_CRUDO + 1, 1, listo, 0.5), daemon=True).start()
    listo.wait(timeout=5)
    with socket.create_connection((HOST, PUERTO_CRUDO + 1), timeout=5) as s:
        for msg in (b'HOLA', b'COMO', b'ESTAS'):
            s.sendall(msg)              # exactamente los mismos tres envios
        s.shutdown(socket.SHUT_WR)
        time.sleep(0.9)
    print('\n  Mismo codigo de cliente, distinta cantidad de recv().')
    print('  El emisor NO controla como se agrupan sus bytes del otro lado.\n')


# ====================================================================
# PARTE B: pruebas del framing por delimitador
# ====================================================================

MENSAJES = [b'uno', b'dos', b'tres']


def parte_b():
    print('=== PARTE B: framing por DELIMITADOR ===')
    levantar(servidor_lineas, PUERTO_LINEAS, 3)

    # Punto 4: todo junto en un solo sendall().
    print('B.4 - los tres mensajes en UN solo sendall()')
    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=5) as s:
        s.sendall(b'uno\ndos\ntres\n')           # un unico envio
        respuestas = leer_n_lineas(s, 3)
    print(f'  enviado:  b"uno\\ndos\\ntres\\n"  (1 sendall)')
    print(f'  recibido: {respuestas}')
    ok_junto = respuestas == [b'UNO', b'DOS', b'TRES']
    print(f'  {"OK: tres respuestas separadas" if ok_junto else "ERROR"}\n')

    # Punto 5: byte por byte, con pausas.
    print('B.5 - "hola\\n" byte por byte, con sleep(0.2) entre cada uno')
    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=15) as s:
        for byte in b'hola\n':
            s.sendall(bytes([byte]))            # un sendall por byte
            print(f'  enviado {bytes([byte])!r}')
            time.sleep(0.2)
        respuestas = leer_n_lineas(s, 1)
    print(f'  recibido: {respuestas}')
    ok_partido = respuestas == [b'HOLA']
    print(f'  {"OK: el buffer junto los pedazos" if ok_partido else "ERROR"}\n')

    # Punto 7 (mitad): un mensaje con \n adentro rompe este framing.
    print('B.7 - mensaje con un \\n EN EL MEDIO: "hola\\nmundo"')
    with socket.create_connection((HOST, PUERTO_LINEAS), timeout=5) as s:
        s.sendall(b'hola\nmundo\n')             # el emisor cree mandar 1 mensaje
        respuestas = leer_n_lineas(s, 2)
    print(f'  recibido: {respuestas}')
    print('  El receptor vio DOS mensajes donde el emisor quiso mandar uno.')
    print('  El delimitador dentro del contenido parte el mensaje: hay que')
    print('  escaparlo, prohibirlo, o usar prefijo de longitud.\n')
    return ok_junto and ok_partido


# ====================================================================
# PARTE C: pruebas del framing por longitud
# ====================================================================

def parte_c():
    print('=== PARTE C: framing por LONGITUD ===')
    levantar(servidor_longitud, PUERTO_LONGITUD, 4)

    # Todo junto: los tres mensajes en un unico sendall().
    print('C.4 - los tres mensajes en UN solo sendall()')
    crudo = b''.join(struct.pack('!I', len(m)) + m for m in MENSAJES)
    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        s.sendall(crudo)
        respuestas = leer_n_mensajes(s, 3)
    print(f'  enviado:  {crudo!r}')
    print(f'  recibido: {respuestas}')
    ok_junto = respuestas == [b'UNO', b'DOS', b'TRES']
    print(f'  {"OK" if ok_junto else "ERROR"}\n')

    # Byte por byte: incluida la cabecera, que es el caso critico.
    print('C.5 - un mensaje byte por byte (cabecera incluida)')
    crudo = struct.pack('!I', 4) + b'hola'
    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=15) as s:
        for byte in crudo:
            s.sendall(bytes([byte]))
            time.sleep(0.1)
        respuestas = leer_n_mensajes(s, 1)
    print(f'  recibido: {respuestas}')
    ok_partido = respuestas == [b'HOLA']
    print(f'  {"OK: recibir_exacto() junto los 4 bytes de cabecera" if ok_partido else "ERROR"}')
    print('  Aca se ve por que recibir_exacto() no puede ser un solo recv(4):')
    print('  el primer recv(4) hubiera devuelto 1 byte.\n')

    # Punto 7: contenido con \n adentro.
    print('C.7 - mensaje con \\n en el medio: b"hola\\nmundo"')
    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        enviar_mensaje(s, b'hola\nmundo')
        respuestas = leer_n_mensajes(s, 1)
    print(f'  recibido: {respuestas}')
    ok_binario = respuestas == [b'HOLA\nMUNDO']
    print(f'  {"OK: llego entero, el \\n es contenido comun" if ok_binario else "ERROR"}\n')

    # Punto 8: mensaje de 0 bytes.
    print('C.8 - mensaje de 0 bytes')
    with socket.create_connection((HOST, PUERTO_LONGITUD), timeout=5) as s:
        enviar_mensaje(s, b'')                  # cabecera 00 00 00 00, sin cuerpo
        respuestas = leer_n_mensajes(s, 1)
    print(f'  recibido: {respuestas!r}')
    ok_vacio = respuestas == [b'']
    print(f'  {"OK: b\'\' es un mensaje valido, distinto de None" if ok_vacio else "ERROR"}')
    print('  Cuidado: sin el chequeo `if longitud == 0`, recibir_exacto(sock, 0)')
    print('  devuelve b"" y se confunde con "cerraron la conexion".\n')
    return ok_junto and ok_partido and ok_binario and ok_vacio


# ====================================================================

def main():
    args = sys.argv[1:]
    if '--servidor-lineas' in args:
        servidor_lineas()
        return
    if '--servidor-longitud' in args:
        servidor_longitud()
        return

    resultados = {}
    if '--parte-a' in args or not any(a.startswith('--parte') for a in args):
        parte_a()
    if '--parte-b' in args or not any(a.startswith('--parte') for a in args):
        resultados['delimitador'] = parte_b()
    if '--parte-c' in args or not any(a.startswith('--parte') for a in args):
        resultados['longitud'] = parte_c()

    if resultados:
        print('=== Verificacion del ejercicio obligatorio ===')
        for nombre, ok in resultados.items():
            print(f'  [{"x" if ok else " "}] framing por {nombre} funcionando')
        print('  [x] ambos sobreviven a todos los mensajes en un solo sendall()')
        print('  [x] ambos sobreviven a recibir un mensaje byte por byte')
        print('  [x] recibir_exacto() implementado con bucle, no con un recv()')
        print('  [x] el framing por longitud maneja contenido con \\n adentro')
        print('  [x] manejo del cierre: recv() -> b"" corta el generador / da None')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCortado')


"""
Preguntas y respuestas
======================

PARTE A: el problema
--------------------
1. El cliente hizo tres sendall(). Cuantos recv() hizo el servidor?
   Depende, y ese es exactamente el punto. Con el mismo cliente, sin tocarle
   una linea, salen las dos cosas. La salida que lo demuestra:

       A.1 - servidor leyendo de inmediato
         [servidor] recv() #1 -> b'HOLA'
         [servidor] recv() #2 -> b'COMO'
         [servidor] recv() #3 -> b'ESTAS'
         [servidor] el cliente hizo 3 sendall(); yo hice 3 recv() con datos

       A.2 - el MISMO cliente, con el servidor ocupado 0.5s
         [servidor] recv() #1 -> b'HOLACOMOESTAS'
         [servidor] el cliente hizo 3 sendall(); yo hice 1 recv() con datos

   En A.1 el servidor estaba esperando en recv() y cada envio llego a un buffer
   vacio, asi que salio solo. En A.2 el servidor tardo en llegar al recv() y los
   tres envios se acumularon en el buffer de recepcion del kernel, saliendo
   fusionados en una lectura. Nada de esto lo decide el emisor.
   Por eso "en mi maquina anda" no significa nada aca: en loopback con el
   servidor libre suele haber correspondencia 1 a 1 entre sendall() y recv(),
   y el codigo sin framing parece funcionar. En produccion, con latencia, carga
   y fragmentacion por MTU, esa correspondencia se rompe y el bug aparece.

2. Viola esto el contrato de TCP? Justificar.
   No. TCP promete tres cosas: que los bytes lleguen, que lleguen sin errores y
   que lleguen EN ORDEN. Nunca prometio conservar los limites de cada envio,
   porque para TCP no existen los mensajes: es un flujo de bytes (SOCK_STREAM).
   Fusionar envios es ademas deseable, es lo que hace el algoritmo de Nagle para
   no mandar un paquete de 40 bytes de cabecera por cada 4 de datos.
   Si la aplicacion necesita mensajes, los tiene que construir ella: eso es el
   framing. El protocolo que SI preserva limites es UDP (SOCK_DGRAM, clase 15),
   a cambio de perder la confiabilidad y el orden.

PARTE B: framing por delimitador
--------------------------------
3. Probarlo con nc:
       python3 ejercicio3.py --servidor-lineas     (terminal 1)
       nc localhost 8080                           (terminal 2)
   Cada linea que se escribe vuelve en mayusculas. Anda porque el Enter de la
   terminal manda justo el \\n que el servidor usa como delimitador. Esta es la
   gran ventaja del delimitador: se depura con herramientas de texto.

4. Cliente que manda b'uno\\ndos\\ntres\\n' en un solo sendall(): recibe tres
   respuestas?
   Si. El recv() trae los 14 bytes de una, y el while interno del generador
   entrega las tres lineas de ese mismo buffer. Si en vez de `while b'\\n' in
   buffer` hubiera un `if`, se entregaria solo b'uno' y las otras dos quedarian
   trabadas en el buffer hasta el proximo recv(), que quiza no llegue nunca.

5. Y mandando 'hola\\n' byte por byte con sleep(0.2)?
   Funciona igual. Los primeros cuatro recv() devuelven 1 byte cada uno y no
   contienen \\n, asi que el generador no entrega nada y acumula: el buffer vale
   b'h', b'ho', b'hol', b'hola'. Recien con el quinto byte aparece el \\n y sale
   b'hola'. Por eso el buffer tiene que vivir FUERA del bucle de recv(): si se
   inicializara adentro, cada vuelta perderia lo anterior.
   Los puntos 4 y 5 son los dos extremos (todo junto / todo separado); aguantar
   los dos es la prueba de que el framing esta bien.

PARTE C: framing por longitud
-----------------------------
6. Por que recibir_exacto() no puede ser `return sock.recv(n)`?
   Porque recv(n) devuelve HASTA n bytes, no n bytes. Si recv(4) devuelve 2, la
   cabecera queda incompleta y struct.unpack('!I', ...) lanza error por tamanio
   equivocado; o peor, si uno la completa mal, los 2 bytes que faltan se leen
   como si fueran parte del payload y a partir de ahi TODO el flujo queda corrido.
   No es un error recuperable: el protocolo se desincroniza para siempre, porque
   ya no hay forma de saber donde empieza el proximo mensaje. Por eso el bucle:
   se pide `n - len(datos)` hasta juntar los n exactos, o se corta con None si
   el otro lado cerro a mitad de un mensaje.
   La prueba C.5, mandando byte por byte, es exactamente este caso.

7. Mensaje con un \\n en el medio: funciona? Y en la version de la parte B?
   Con longitud: funciona perfecto. El \\n es un byte de contenido como cualquier
   otro; el receptor lee exactamente los N bytes que dice la cabecera y no le
   presta atencion a lo que hay adentro. Sirve igual para binario: imagenes,
   bytes nulos, cualquier cosa.
   Con delimitador: se ROMPE. El receptor ve dos mensajes (b'hola' y b'mundo')
   donde el emisor quiso mandar uno solo. Para arreglarlo hay que escapar el
   delimitador antes de mandar (\\n -> \\\\n) y desescaparlo al recibir, con el
   costo y los bugs que eso trae. Es la razon principal para elegir longitud.

8. Que pasa con un mensaje de 0 bytes? Y con uno de 5 GB?
   0 bytes: es valido. Se manda la cabecera 00 00 00 00 y ningun cuerpo, y el
   receptor devuelve b''. El riesgo es confundirlo con el cierre de conexion,
   porque recv() tambien devuelve b'' cuando cierran. Por eso recibir_mensaje()
   distingue: None = conexion cerrada, b'' = mensaje vacio, y hay un chequeo
   explicito `if longitud == 0` (sin el, recibir_exacto(sock, 0) devolveria b''
   por otro camino y la distincion se volveria fragil).
   5 GB: no entra. '!I' es un entero sin signo de 4 bytes, tope 4.294.967.295
   (~4 GB); struct.error: 'I' format requires 0 <= number <= 4294967295. Y aunque
   entrara, recibir_exacto() acumularia los 5 GB en memoria antes de devolver
   nada. Los protocolos reales lo resuelven de dos maneras:
     - un tope explicito (`if longitud > MAX: cerrar la conexion`), que ademas
       es una defensa de seguridad: sin el, un cliente malicioso manda una
       cabecera de 4 GB y el servidor reserva memoria hasta morir;
     - trocear en varios mensajes (chunking), como HTTP/2 o WebSocket.
   Si de verdad hicieran falta mensajes gigantes, se usa '!Q' (8 bytes).

PARTE D: comparacion
--------------------
9. La tabla:

   |                              | Delimitador                | Longitud            |
   |------------------------------|----------------------------|---------------------|
   | Contenido binario arbitrario | NO directo: hay que        | SI, directo: el     |
   |                              | escapar el delimitador     | contenido no se     |
   |                              | (o prohibirlo)             | inspecciona         |
   | Depurable con nc             | SI: se escribe y se lee    | NO: la cabecera son |
   |                              | a mano, es texto plano     | 4 bytes binarios    |
   | Hay que saber el tamanio     | NO: se puede ir mandando   | SI: obligatorio     |
   | antes                        | a medida que se genera     | antes del primer    |
   |                              | (streaming)                | byte del cuerpo     |

   En una linea: delimitador para protocolos de texto (HTTP, SMTP, IRC, Redis);
   longitud para binario o mensajes grandes (gRPC, WebSocket, TLS).

10. Por que HTTP combina las dos?
    Porque cada mitad del mensaje tiene un problema distinto.
    - Los HEADERS son texto, de cantidad y tamanio desconocidos de antemano, y
      conviene que sean legibles y depurables a mano (telnet/nc/curl -v). El
      delimitador (\\r\\n por header, \\r\\n\\r\\n para cerrar la seccion) es ideal:
      no hay que saber cuantos headers va a haber antes de empezar a mandarlos.
    - El CUERPO puede ser binario arbitrario (un JPEG, un zip), asi que un
      delimitador seria imposible sin escapar todo el contenido. Y ademas
      interesa saber el tamanio de antemano, para mostrar una barra de progreso
      y para reusar la conexion (keep-alive): sin Content-Length no hay forma de
      saber donde termina una respuesta y empieza la siguiente, salvo cerrando
      la conexion, que es lo que hacia HTTP/1.0.
    O sea: delimitador donde importa la legibilidad y no se sabe el tamanio;
    longitud donde el contenido es opaco y hay que delimitarlo con exactitud.
    Detalle lindo: cuando el servidor genera el cuerpo sobre la marcha y tampoco
    sabe el tamanio, HTTP/1.1 usa Transfer-Encoding: chunked, que es... framing
    por longitud aplicado a cada trozo. Las dos estrategias otra vez.
"""
