#!/usr/bin/env python3
"""Ejercicio 5: Errores y timeouts.

    python3 ejercicio5.py --rechazada     # 5.1 punto 1
    python3 ejercicio5.py --reintentos    # 5.1 puntos 2 y 3
    python3 ejercicio5.py --sin-timeout   # 5.2 punto 4 (cuelga; Ctrl+C)
    python3 ejercicio5.py --timeout       # 5.2 punto 5
    python3 ejercicio5.py --robusto       # 5.3 punto 7
    python3 ejercicio5.py                 # todo menos --sin-timeout
"""
import socket
import struct
import sys
import threading
import time

HOST = '127.0.0.1'
PUERTO_MUERTO = 8199        # nadie escucha nunca aca
PUERTO_TARDIO = 8096        # el servidor aparece unos segundos despues
PUERTO_MUDO = 8097          # acepta pero no responde nunca
PUERTO_ROBUSTO = 8098


# --------------------------------------------------------------------
# 5.1 Conexion rechazada
# --------------------------------------------------------------------

def rechazada():
    print('=== 5.1 punto 1: nadie escuchando ===')
    inicio = time.perf_counter()
    try:
        with socket.create_connection((HOST, PUERTO_MUERTO), timeout=5):
            pass
    except ConnectionRefusedError as e:
        transcurrido = time.perf_counter() - inicio
        print(f'  {type(e).__name__}: {e}')
        print(f'  tardo {transcurrido:.3f}s')
        if transcurrido < 0.2:
            print('  Practicamente instantaneo: el kernel destino contesta un')
            print('  RST, un "no" explicito. No hubo que esperar un timeout.')
        else:
            print('  En Linux esto es instantaneo (~0.001s): llega un RST.')
            print('  En Windows tarda ~2s porque reintenta el SYN antes de')
            print('  darse por vencido. La excepcion es la misma; lo que')
            print('  cambia es cuanto tarda en aparecer.')
    print()


def conectar_con_reintentos(host, puerto, intentos=5, espera_inicial=0.5,
                            factor=2.0, tope=8.0):
    """Reintenta hasta que el servidor aparezca, con backoff exponencial.

    Devuelve el socket conectado, o lanza ConnectionError si se agotaron los
    intentos. El backoff evita machacar al servidor que esta arrancando.
    """
    espera = espera_inicial
    for intento in range(1, intentos + 1):
        try:
            # timeout holgado: en Windows el rechazo tarda ~2s en reportarse,
            # y con timeout=2 saltaria TimeoutError en vez del error real.
            sock = socket.create_connection((host, puerto), timeout=5)
            print(f'  intento {intento}: conectado')
            return sock
        except (ConnectionRefusedError, TimeoutError, OSError) as e:
            if intento == intentos:
                break                       # no dormir despues del ultimo
            print(f'  intento {intento} fallo ({type(e).__name__}). '
                  f'Reintento en {espera:.1f}s')
            time.sleep(espera)
            espera = min(espera * factor, tope)     # backoff con techo
    raise ConnectionError(
        f'No se pudo conectar a {host}:{puerto} tras {intentos} intentos')


def servidor_tardio(puerto, demora):
    """Aparece recien despues de `demora` segundos."""
    time.sleep(demora)
    print(f'  [servidor] arranco recien ahora, tras {demora}s')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(1)
        conn, _dir = srv.accept()
        with conn:
            datos = conn.recv(4096)
            conn.sendall(b'ECHO: ' + datos)


def reintentos():
    print('=== 5.1 puntos 2 y 3: reintentos con backoff ===')
    print('  lanzo el cliente primero y el servidor 3 segundos despues')
    threading.Thread(target=servidor_tardio, args=(PUERTO_TARDIO, 3.0),
                     daemon=True).start()
    inicio = time.perf_counter()
    try:
        with conectar_con_reintentos(HOST, PUERTO_TARDIO) as s:
            s.sendall(b'llegue igual\n')
            print(f'  respuesta: {s.recv(4096)!r}')
            print(f'  total: {time.perf_counter() - inicio:.1f}s')
    except ConnectionError as e:
        print(f'  {e}')
    print()


# --------------------------------------------------------------------
# 5.2 Timeouts
# --------------------------------------------------------------------

def servidor_mudo(puerto, listo, conexiones=2):
    """Acepta la conexion y no manda nada nunca."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        listo.set()
        conns = []
        for _ in range(conexiones):
            conn, _dir = srv.accept()
            conns.append(conn)              # las guardo abiertas, sin responder
        time.sleep(30)
        for c in conns:
            c.close()


def sin_timeout():
    print('=== 5.2 punto 4: recv() sin timeout ===')
    listo = threading.Event()
    threading.Thread(target=servidor_mudo, args=(PUERTO_MUDO, listo, 1),
                     daemon=True).start()
    listo.wait(timeout=5)
    with socket.create_connection((HOST, PUERTO_MUDO)) as s:
        print(f'  timeout del socket: {s.gettimeout()} (None = sin limite)')
        print('  llamando a recv() sin mandar nada... esto NO vuelve solo.')
        print('  (Ctrl+C para salir)')
        datos = s.recv(4096)                # se queda aca para siempre
        print(f'  recibido: {datos!r}')


def con_timeout():
    print('=== 5.2 punto 5: el mismo recv() con settimeout(3) ===')
    listo = threading.Event()
    threading.Thread(target=servidor_mudo, args=(PUERTO_MUDO, listo, 1),
                     daemon=True).start()
    listo.wait(timeout=5)
    with socket.create_connection((HOST, PUERTO_MUDO)) as s:
        s.settimeout(3)
        print(f'  timeout del socket: {s.gettimeout()}s')
        inicio = time.perf_counter()
        try:
            datos = s.recv(4096)
            print(f'  recibido: {datos!r}')
        except TimeoutError as e:
            # socket.timeout es un alias de TimeoutError desde Python 3.10.
            print(f'  {type(e).__name__}: {e}')
            print(f'  volvio a los {time.perf_counter() - inicio:.1f}s, '
                  f'y el programa sigue vivo')
    print()


# --------------------------------------------------------------------
# 5.3 Servidor robusto
# --------------------------------------------------------------------

def servidor_robusto(puerto, listo, conexiones=2):
    """El try/except del echo_server.py: un cliente que corta mal no lo tumba."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        listo.set()
        for i in range(conexiones):
            conn, direccion = srv.accept()
            try:
                with conn:
                    while True:
                        datos = conn.recv(4096)
                        if not datos:
                            break
                        time.sleep(0.3)     # trabajo: da tiempo a que corten
                        conn.sendall(datos)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f'  [servidor] cliente {direccion} corto mal: '
                      f'{type(e).__name__}. Sigo vivo.')
            else:
                print(f'  [servidor] cliente {direccion} cerro bien.')
        print('  [servidor] atendi las dos conexiones sin morirme')


def robusto():
    print('=== 5.3 punto 7: cliente que corta abruptamente ===')
    listo = threading.Event()
    hilo = threading.Thread(target=servidor_robusto,
                            args=(PUERTO_ROBUSTO, listo, 2), daemon=True)
    hilo.start()
    listo.wait(timeout=5)

    # Cliente 1: corta de la peor manera posible. SO_LINGER en 0 hace que
    # close() mande un RST en vez del FIN ordenado; es lo que ve el servidor
    # cuando a un nc lo matan con Ctrl+C a mitad de una transferencia.
    s = socket.create_connection((HOST, PUERTO_ROBUSTO), timeout=5)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                 struct.pack('ii', 1, 0))
    s.sendall(b'no pienso esperar la respuesta\n')
    s.close()                               # RST
    time.sleep(1.0)

    # Cliente 2: el servidor tiene que seguir andando para este.
    with socket.create_connection((HOST, PUERTO_ROBUSTO), timeout=5) as s2:
        s2.sendall(b'sigo funcionando\n')
        print(f'  cliente 2 recibio: {s2.recv(4096)!r}')
    hilo.join(timeout=3)
    print()


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if '--sin-timeout' in args:
            sin_timeout()
        elif args:
            if '--rechazada' in args:
                rechazada()
            if '--reintentos' in args:
                reintentos()
            if '--timeout' in args:
                con_timeout()
            if '--robusto' in args:
                robusto()
        else:
            rechazada()
            reintentos()
            con_timeout()
            robusto()
            print('Falta --sin-timeout: se cuelga a proposito, va aparte.')
    except KeyboardInterrupt:
        print('\n  Cortado con Ctrl+C: eso es exactamente lo que pasa cuando')
        print('  un cliente sin timeout espera a un servidor que no contesta.')


"""
Preguntas y respuestas
======================

5.1 Conexion rechazada
----------------------
1. Sin ningun servidor corriendo, que excepcion da el cliente?
       ConnectionRefusedError: [Errno 111] Connection refused        (Linux)
       ConnectionRefusedError: [WinError 10061] ...                  (Windows)
   Es subclase de ConnectionError, que a su vez es subclase de OSError.
   El mecanismo: el kernel de la maquina destino ve un SYN dirigido a un puerto
   donde nadie hizo listen() y contesta un RST, o sea un "no" explicito. No hace
   falta esperar ningun timeout, porque hubo respuesta.
   Cuanto tarda depende del sistema, y conviene medirlo en vez de suponerlo:
   - Linux: ~0.001s, practicamente instantaneo.
   - Windows (medido en esta maquina, 3 corridas): 2.03-2.05s, siempre. Windows
     reintenta el SYN un par de veces antes de dar por buena la negativa.
   La excepcion es la misma; lo que cambia es la demora. Detalle practico: por
   eso conectar_con_reintentos() usa timeout=5 y no 2, porque con timeout=2 en
   Windows saltaria TimeoutError antes de que llegue el ConnectionRefusedError,
   y el diagnostico quedaria equivocado.
   Caso distinto es un host inexistente o un firewall que DESCARTA los paquetes
   en silencio: ahi no vuelve nada, connect() se queda esperando y lo que salta
   es TimeoutError (o OSError: No route to host) muchos segundos despues.
   Distinguirlos sirve para diagnosticar: rechazo = la maquina esta pero el
   servicio no; demora larga sin respuesta = no se llega, o hay un firewall.

2. Cliente con reintentos y backoff: ver conectar_con_reintentos() arriba.
   Tres detalles que importan:
   - Se capturan ConnectionRefusedError y TimeoutError, no Exception a secas:
     un error de DNS o de permisos no se arregla reintentando.
   - La espera CRECE (0.5, 1, 2, 4, 8...) en vez de ser fija. Reintentar cada
     100 ms contra un servidor que esta arrancando lo unico que hace es
     sumarle carga justo en el peor momento. Con un techo (`tope`) para que la
     espera no se vaya a minutos.
   - Hay un limite de intentos y despues se lanza una excepcion. Un reintento
     infinito esconde la falla: el programa parece colgado y nadie sabe por que.
   En produccion se le suele agregar jitter (un valor aleatorio a la espera)
   para que mil clientes que se cayeron juntos no vuelvan todos exactamente al
   mismo tiempo, que es la estampida clasica.

3. Lanzando el cliente primero y el servidor 3 segundos despues: el cliente
   falla en los primeros intentos, va esperando cada vez mas, y engancha
   apenas el servidor hace listen(). El total ronda los 3-4 segundos. La
   salida muestra los intentos fallidos y despues el ECHO.

5.2 Timeouts
------------
4. Cliente que se conecta, no manda nada, e intenta recv(): que pasa?
   Se cuelga. Para siempre. El socket viene con timeout None (bloqueante sin
   limite), asi que recv() duerme el proceso esperando datos que no van a
   llegar nunca, porque el servidor esta esperando que el cliente hable primero.
   No consume CPU (esta bloqueado, no girando), pero el programa esta muerto:
   la unica salida es Ctrl+C o matar el proceso. Es un deadlock distribuido,
   cada lado esperando al otro.

5. Con s.settimeout(3): que excepcion da?
       TimeoutError: timed out
   A los 3 segundos exactos. Desde Python 3.10, socket.timeout es un alias de
   TimeoutError (antes era una clase aparte), asi que se puede capturar
   `except TimeoutError`. Lo clave es que el control VUELVE al programa: se
   puede reintentar, loguear, avisar al usuario o cerrar la conexion, en vez de
   quedar colgado.
   Ojo con un detalle: settimeout() aplica a CADA operacion por separado, no al
   total. Un recv() en bucle con timeout de 3s puede tardar horas si el servidor
   manda un byte cada 2 segundos. Para acotar el total hay que llevar la cuenta
   aparte.
   Ademas, settimeout() pone el socket en modo no bloqueante por dentro; por eso
   no se puede combinar con setblocking(False) a mano.

6. Por que un cliente sin timeout es peligroso en produccion?
   Porque un servidor que no responde deja de ser un error y pasa a ser un
   cuelgue silencioso, y eso se propaga:
   - El hilo o proceso que hizo el recv() queda bloqueado indefinidamente. Si
     hay un pool de N workers, alcanzan N clientes lentos para dejar el
     servicio entero sin capacidad, aunque la maquina este ociosa.
   - No hay error, no hay excepcion, no hay log. El monitoreo ve "todo bien"
     mientras el sistema no atiende a nadie. Es mucho peor que fallar rapido.
   - Se encadena: si A espera a B para siempre, y C espera a A, la caida de un
     solo servicio de tercera linea tumba toda la cadena. Es el modo de falla
     tipico de los microservicios.
   - Nada garantiza que llegue un error: si la maquina remota se apaga de golpe
     o se cae la red, no hay FIN ni RST que avise. Sin timeout, el recv() puede
     esperar literalmente para siempre.
   Esto conecta con la falacia numero 2 de la computacion distribuida vista en
   la clase 12: "la latencia es cero". No lo es, a veces es infinita, y el
   timeout es la forma de admitirlo en el codigo.

5.3 Servidor robusto
--------------------
7. Con el servidor corriendo, matar el nc con Ctrl+C: sobrevive el servidor?
   Si, gracias al try/except. Lo que ve el servidor es una de dos cosas:
   - si el cliente cerro ordenadamente, recv() devuelve b'' y el bucle corta
     normal (no es un error);
   - si el cliente murio de golpe con datos en vuelo, llega un RST y salta
     ConnectionResetError o BrokenPipeError.
   Sin el try/except, esa excepcion escapa del bucle de accept(), el servidor
   termina, y el resto de los clientes queda sin servicio: un cliente
   cualquiera puede tumbar el servidor entero, lo que ademas es una via de
   denegacion de servicio trivial.
   En el codigo lo forzamos con SO_LINGER en 0, que hace que close() mande un
   RST en vez del FIN ordenado: es la version reproducible del Ctrl+C.

8. Que excepciones captura echo_server.py y por que esas?
   Captura (ConnectionResetError, BrokenPipeError, OSError):
   - ConnectionResetError: el otro lado corto de golpe (RST). Es lo que llega
     al LEER de una conexion que murio mal.
   - BrokenPipeError: es lo que llega al ESCRIBIR en una conexion que el otro
     lado ya cerro. Son las dos caras del mismo evento, segun quien lo detecte
     primero. (En Unix ademas llega la senial SIGPIPE, que Python convierte en
     esta excepcion.)
   - OSError: la clase padre de todas las de socket, como red de contencion
     para los errores raros del sistema (Errno 113 no route to host, un
     descriptor invalido, etc.).
   La logica del diseno es la que importa: se capturan los errores ESPERABLES
   de una conexion individual, y se los trata como "este cliente se fue",
   no como "el servidor fallo". Cada conexion es independiente, asi que el
   error se contiene en su propio alcance y el bucle sigue.
   Lo que NO se hace es un `except Exception` que se trague todo: un
   TypeError o un KeyError son bugs propios, y esconderlos convierte un
   servidor roto en un servidor que devuelve basura sin avisar.
   Detalle: en el echo_server.py de la clase, el try/except esta en
   atender_seguro(), que envuelve el trabajo de UN hilo. Asi la excepcion se
   lleva puesto ese hilo y ningun otro, que es exactamente lo que se busca.
"""
