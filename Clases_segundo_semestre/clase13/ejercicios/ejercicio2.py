#!/usr/bin/env python3
"""Ejercicio 2: Entender recv().

Trae su propio servidor eco interno (en un hilo), asi que corre solo, sin
necesitar dos terminales ni netcat. Con --externo se conecta al
echo_server.py de la clase en vez de al interno.

    python3 ejercicio2.py --parcial            # 2.1: lecturas parciales
    python3 ejercicio2.py --parcial --tope 1   # 2.1 punto 2: recv(1)
    python3 ejercicio2.py --parcial --tope 65536
    python3 ejercicio2.py --sin-chequeo        # 2.2 punto 4: el bug numero uno
    python3 ejercicio2.py --con-chequeo        # 2.2 punto 5: arreglado
    python3 ejercicio2.py --send               # 2.3 punto 8: 10 MB con un send()
    python3 ejercicio2.py                      # corre todo
"""
import socket
import sys
import threading
import time

HOST = '127.0.0.1'
PUERTO = 8090            # distinto de 8080 para no chocar con echo_server.py
PUERTO_SORDO = 8091      # receptor que acepta y nunca lee (punto 8)
TIMEOUT = 10


# --------------------------------------------------------------------
# Servidor eco interno (para que el ejercicio corra solo)
# --------------------------------------------------------------------

def servidor_eco(puerto, conexiones=1, listo=None):
    """Eco simple: devuelve todo lo que le mandan hasta que el cliente cierre."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(5)
        if listo:
            listo.set()                     # avisar que ya se puede conectar
        for _ in range(conexiones):
            conn, _dir = srv.accept()
            total = 0
            try:
                with conn:
                    while True:
                        datos = conn.recv(65536)
                        if not datos:
                            break           # el cliente cerro limpio: fin
                        total += len(datos)
                        conn.sendall(datos)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                # Un cliente que corta mal no debe tumbar al servidor: si esta
                # excepcion escapara, moriria el hilo y las conexiones
                # siguientes recibirian ConnectionRefusedError.
                print(f'  [servidor] desconexion abrupta tras {total} bytes: '
                      f'{type(e).__name__}')
                continue
            print(f'  [servidor] el cliente cerro tras {total} bytes')


def servidor_sordo(puerto, listo):
    """Acepta la conexion y NO lee nunca.

    Sirve para el punto 8: si nadie vacia el buffer de recepcion, el buffer de
    envio del emisor se llena y send() no tiene mas remedio que mandar de menos.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Buffer de recepcion chico, puesto ANTES del listen() para que lo
        # herede el socket que devuelve accept(). En loopback el kernel usa
        # buffers enormes por defecto y el efecto no se veria.
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8192)
        srv.bind((HOST, puerto))
        srv.listen(5)
        listo.set()
        conn, _dir = srv.accept()
        with conn:
            time.sleep(8)               # acepta, se queda mudo, y despues cierra


def levantar_servidor(conexiones=1, puerto=PUERTO):
    """Arranca el servidor en un hilo y espera a que este escuchando."""
    listo = threading.Event()
    hilo = threading.Thread(target=servidor_eco,
                            args=(puerto, conexiones, listo), daemon=True)
    hilo.start()
    listo.wait(timeout=5)
    return hilo


# --------------------------------------------------------------------
# 2.1 Lecturas parciales
# --------------------------------------------------------------------

def parcial(tope=4, puerto=PUERTO):
    """Lee de a `tope` bytes para hacer visible que recv() devuelve lo que hay."""
    mensaje = b'un mensaje bastante mas largo que cuatro bytes\n'
    print(f'--- 2.1 recv({tope}) sobre {len(mensaje)} bytes ---')
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        s.sendall(mensaje)
        s.shutdown(socket.SHUT_WR)      # "no mando mas"; el server vera b''
        recibido = b''
        llamadas = 0
        tamanios = []
        while True:
            pedazo = s.recv(tope)       # tope, NO cantidad pedida
            llamadas += 1
            if not pedazo:
                break                   # b'' = el otro lado cerro
            tamanios.append(len(pedazo))
            recibido += pedazo
    print(f'  llamadas a recv({tope}): {llamadas} '
          f'({llamadas - 1} con datos + 1 que devolvio b"")')
    print(f'  tamanios devueltos: {tamanios}')
    print(f'  recibidos {len(recibido)} de {len(mensaje)} bytes enviados')
    print(f'  integridad: {"OK, no se perdio nada" if recibido == mensaje else "ERROR"}')
    return llamadas, tamanios


# --------------------------------------------------------------------
# 2.2 La senial de cierre
# --------------------------------------------------------------------

def sin_chequeo(puerto=PUERTO):
    """El bug numero uno: while True sin chequear b''.

    Version acotada para que no cuelgue la maquina: en vez de girar para
    siempre, corta a las 200.000 vueltas y mide cuanto tardo.
    """
    print('--- 2.2 punto 4: bucle SIN el chequeo de cierre ---')
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        s.sendall(b'test\n')
        s.recv(4096)                    # consumo el eco
        s.shutdown(socket.SHUT_WR)      # provoco que el servidor cierre
        time.sleep(0.3)
        vueltas = 0
        inicio = time.perf_counter()
        while vueltas < 200_000:        # tope artificial: si no, es infinito
            datos = s.recv(4096)
            vueltas += 1
            if vueltas <= 3:
                print(f'  recv devolvio: {datos!r}')
            # OJO: falta el chequeo de cierre
        transcurrido = time.perf_counter() - inicio
    print(f'  {vueltas} recv() en {transcurrido:.2f}s '
          f'({vueltas / transcurrido:,.0f} por segundo)')
    print('  Cada uno devuelve b"" al instante: no bloquea, no espera nada.')
    print('  Eso es un bucle ocupado quemando un nucleo al 100%.')


def con_chequeo(puerto=PUERTO):
    """Lo mismo, con el chequeo que faltaba."""
    print('--- 2.2 punto 5: el mismo bucle CON el chequeo ---')
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        s.sendall(b'test\n')
        s.shutdown(socket.SHUT_WR)
        vueltas = 0
        while True:
            datos = s.recv(4096)
            vueltas += 1
            print(f'  recv devolvio: {datos!r}')
            if not datos:               # <-- ESTE es el chequeo que falta
                print('  El servidor cerro la conexion; salgo del bucle.')
                break
    print(f'  termino en {vueltas} vueltas')


# --------------------------------------------------------------------
# 2.3 send() contra sendall()
# --------------------------------------------------------------------

def prueba_send(puerto=PUERTO):
    """Un solo send() de 10 MB contra un receptor que no lee."""
    print('--- 2.3 punto 8: un unico send() de 10 MB ---')
    datos = b'x' * (10 * 1024 * 1024)

    # Caso A: el receptor NO lee. El buffer se llena y send() manda de menos.
    listo = threading.Event()
    threading.Thread(target=servidor_sordo, args=(PUERTO_SORDO, listo),
                     daemon=True).start()
    listo.wait(timeout=5)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Buffer de envio chico y explicito: en loopback el default es enorme y
    # los 10 MB entrarian enteros, escondiendo justo lo que hay que ver.
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
    with s:
        s.connect((HOST, PUERTO_SORDO))
        print(f'  SO_SNDBUF del emisor: '
              f'{s.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF):,} bytes')
        # No bloqueante: send() copia lo que entra AHORA y vuelve enseguida.
        # Es la unica forma de ver el envio parcial en Windows, donde un send()
        # bloqueante no retorna hasta haber copiado todo (ver punto 8).
        s.setblocking(False)
        enviados = s.send(datos)        # UNA sola llamada, a proposito
        print(f'  contra un receptor que no lee:')
        print(f'    send() devolvio {enviados:,} de {len(datos):,} bytes')
        faltan = len(datos) - enviados
        if faltan:
            print(f'    quedaron {faltan:,} bytes SIN mandar '
                  f'({faltan / len(datos):.1%} del mensaje)')
            print('    y NO hubo ninguna excepcion: ese es el bug silencioso')
            print('    si el codigo asumiera que mando todo, el mensaje llega')
            print('    truncado y nadie se entera')
        else:
            print('    entro TODO igual. Pasa en Windows sobre loopback: el')
            print('    kernel absorbe cualquier tamanio y hasta ignora el')
            print('    SO_SNDBUF que le pedimos. En Linux, o por red real,')
            print('    esta misma llamada devuelve una fraccion. Ver punto 8.')

    # Caso B: el receptor lee todo el tiempo, con buffers por defecto. Aca suele
    # entrar completo, y por eso el bug no se ve en desarrollo.
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        enviados = s.send(datos)
        print(f'  contra un receptor que lee al mismo tiempo (buffers default):')
        print(f'    send() devolvio {enviados:,} de {len(datos):,} bytes')
        vaciar(s)

    # La version correcta: sendall() insiste hasta terminar.
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        s.sendall(datos)                # no devuelve nada: o manda todo o explota
        print(f'  sendall() devolvio None y mando los {len(datos):,} bytes')
        vaciar(s)

    # Lo que sendall() hace por dentro, escrito a mano. Este es el bucle que
    # hay que escribir si uno insiste en usar send(). En Windows/loopback da
    # una sola vuelta; en Linux o por red da varias.
    with socket.create_connection((HOST, puerto), timeout=TIMEOUT) as s:
        enviado_total = 0
        vueltas = 0
        while enviado_total < len(datos):
            n = s.send(datos[enviado_total:])   # mandar lo que falta
            enviado_total += n
            vueltas += 1
        print(f'  bucle manual con send(): {vueltas} llamada(s) para '
              f'{enviado_total:,} bytes')
        vaciar(s)


def vaciar(sock):
    """Avisa que no se manda mas y consume el eco hasta el cierre.

    Sin esto, cerrar el socket dejando datos sin leer provoca un RST y el
    servidor ve una ConnectionResetError.
    """
    sock.shutdown(socket.SHUT_WR)
    while sock.recv(65536):
        pass


# --------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    externo = '--externo' in args
    puerto = 8080 if externo else PUERTO

    tope = 4
    if '--tope' in args:
        tope = int(args[args.index('--tope') + 1])

    modos = [a for a in args if a in ('--parcial', '--sin-chequeo',
                                      '--con-chequeo', '--send')]
    if not modos:
        modos = ['--parcial', '--sin-chequeo', '--con-chequeo', '--send']

    # Cada prueba usa su propia conexion; prueba_send usa tres del eco
    # (send, sendall y bucle manual) mas una del servidor sordo.
    conexiones = sum(3 if m == '--send' else 1 for m in modos)
    if not externo:
        levantar_servidor(conexiones=conexiones, puerto=puerto)

    for modo in modos:
        if modo == '--parcial':
            parcial(tope, puerto)
        elif modo == '--sin-chequeo':
            sin_chequeo(puerto)
        elif modo == '--con-chequeo':
            con_chequeo(puerto)
        elif modo == '--send':
            prueba_send(puerto)
        print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCortado')
    except ConnectionRefusedError:
        print('No hay servidor. Con --externo hace falta echo_server.py en 8080.')


"""
Preguntas y respuestas
======================

2.1 Lecturas parciales
----------------------
1. Cuantas veces se ejecuto el recv(4)? Se perdio algun byte?
   Con un mensaje de 47 bytes, doce veces con datos (11 de 4 bytes + 1 de 3)
   mas una ultima que devuelve b''. No se perdio nada: el total recibido es
   igual al total enviado. recv() no descarta, sencillamente entrega de a poco.
   El numero exacto depende de como el kernel haya agrupado los datos.

2. Que pasa con recv(1)? Y con recv(65536)?
   recv(1): 47 llamadas con datos, byte por byte. Mucho mas syscalls para el
   mismo resultado; el contenido llega igual de intacto, solo mas lento.
   recv(65536): normalmente UNA sola llamada devuelve los 47 bytes, porque ya
   estaban todos en el buffer de recepcion. Pero eso es suerte, no garantia.

3. Por que recv(65536) no devuelve necesariamente todo de una vez?
   Porque el argumento es un TOPE, no una cantidad pedida. recv() devuelve
   apenas hay algo disponible en el buffer del kernel: no espera a llenar el
   buffer ni a que "termine el mensaje" (TCP no sabe que es un mensaje).
   Si el emisor mando 100 KB y por la red llegaron 1400 bytes hasta ahora,
   recv(65536) devuelve esos 1400. En loopback casi siempre llega todo junto,
   lo que hace que el bug no se vea en desarrollo y aparezca en produccion.

2.2 La senial de cierre
-----------------------
4. Que pasa al matar el servidor con Ctrl+C?
   recv() empieza a devolver b'' INMEDIATAMENTE y para siempre. Como el bucle
   no lo chequea, imprime `recv devolvio: b''` a toda velocidad, miles de veces
   por segundo, hasta que uno corta con Ctrl+C. (En el codigo lo acoto a
   200.000 vueltas para poder medirlo sin colgar la maquina.)

5. Cual es el chequeo que falta?
       if not datos:
           break
   Equivalente: `if datos == b'':`. Es la senial de fin de conexion (el FIN de
   TCP). Hay que chequearla SIEMPRE despues de cada recv().

6. Por que un while True sin ese chequeo consume 100% de CPU?
   Porque recv() sobre una conexion cerrada NO bloquea. Bloquear implica que el
   kernel duerme el proceso hasta que haya algo; pero aca ya hay una respuesta
   definitiva ("no va a venir nada mas"), asi que retorna al instante. El bucle
   pasa a ser un bucle ocupado (busy loop): millones de syscalls por segundo,
   un nucleo al 100%, y ningun progreso. Es el bug numero uno de quien empieza.

2.3 send() contra sendall()
---------------------------
7. Que devuelve cada uno?
   send(datos)    -> int: la cantidad de bytes que efectivamente se copiaron al
                     buffer de envio del kernel. Puede ser menor que len(datos).
                     Nunca es 0 en un socket bloqueante con datos por mandar.
   sendall(datos) -> None. Insiste en un bucle interno hasta mandar todo, o
                     lanza excepcion (BrokenPipeError, ConnectionResetError).
   Aclaracion importante: que send() "mando" los bytes significa que el kernel
   los acepto, NO que el otro lado los recibio ni los leyo.

8. Cliente que manda 10 MB con un solo send(): mando todo?
   Depende de la plataforma, y conviene ser preciso porque es facil sacar la
   conclusion equivocada segun donde se pruebe.

   En Linux (o por red real): NO. El buffer de envio del kernel ronda decenas o
   cientos de KB, no 10 MB, asi que send() devuelve tipicamente entre ~64 KB y
   ~2 MB y el resto queda sin enviar. No lanza ninguna excepcion: el programa
   sigue como si nada, con el mensaje truncado. Ese es el bug silencioso.

   En Windows sobre loopback (lo que da al correr este archivo en esta maquina):
   send() devuelve los 10.485.760 bytes completos. Y sigue devolviendolos
   completos aunque uno ponga SO_SNDBUF en 8192, el receptor no lea nunca, el
   socket sea no bloqueante y el payload suba a 100 MB. Lo probamos: el kernel
   absorbe todo. Ademas, Winsock define que un send() BLOQUEANTE no retorna
   hasta haber copiado todos los bytes, con lo cual en Windows send() se
   comporta de hecho como sendall() en el caso comun.

   La conclusion practica NO cambia, y de hecho es peor: el comportamiento de
   send() depende del sistema operativo, del tamanio de los buffers, de si el
   receptor esta leyendo y de la latencia de la red. Codigo que anda perfecto en
   la notebook con Windows manda mensajes truncados al desplegarlo en un
   servidor Linux. Por eso la regla es sendall(), no "probalo y fijate".

   El bucle manual del final del codigo es lo que sendall() hace por dentro:
       while enviado_total < len(datos):
           n = s.send(datos[enviado_total:])
           enviado_total += n
   En esta maquina termina en 1 vuelta; en Linux, en varias. Escribirlo bien una
   vez es exactamente el trabajo que sendall() ya hizo por nosotros.

9. Cuando podria ser preferible send() a sendall()?
   Cuando uno quiere manejar el envio parcial a mano y no bloquear:
   - Sockets no bloqueantes o con select()/epoll: ahi el patron es mandar lo que
     entre, guardar el resto en una cola de salida y reintentar cuando el socket
     avise que se puede escribir. sendall() bloquearia el hilo, que es justo lo
     que un servidor multiplexado quiere evitar (clase 17).
   - Cuando hace falta contabilidad fina del progreso (barra de progreso,
     control de flujo propio, cancelar a mitad de un envio grande).
   - Con timeout puesto: si sendall() corta por timeout, no hay forma de saber
     cuanto alcanzo a mandar; con send() si.
   Fuera de esos casos, sendall() siempre.
"""
