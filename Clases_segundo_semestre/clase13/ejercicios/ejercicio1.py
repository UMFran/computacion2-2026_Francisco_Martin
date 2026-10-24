#!/usr/bin/env python3
"""Ejercicio 1: Primer contacto (cliente, servidor y SO_REUSEADDR).

Tres modos, para no depender de tener `nc` instalado (en Windows no viene):

    python3 ejercicio1.py --cliente          # 1.1: cliente contra nc -l 8080
    python3 ejercicio1.py --cliente --mudo   # 1.1 punto 3: sin recv()
    python3 ejercicio1.py --servidor         # 1.2: servidor contra nc localhost 8080
    python3 ejercicio1.py --servidor --loop  # 1.2 punto 5: atiende para siempre
    python3 ejercicio1.py --servidor --sin-reuse   # 1.3: sin SO_REUSEADDR
    python3 ejercicio1.py --demo             # todo junto en un solo proceso

Para 1.1 hace falta un `nc -l 8080` (o el modo --servidor de este mismo
archivo) en otra terminal. Para 1.2, un `nc localhost 8080` (o el modo
--cliente).
"""
import socket
import sys
import threading
import time

# 127.0.0.1 y no 'localhost': en Windows ese nombre resuelve primero a ::1
# (IPv6) y el servidor escucha en IPv4, asi que se paga un intento fallido.
HOST_CLIENTE = '127.0.0.1'
HOST_SERVIDOR = '0.0.0.0'
PUERTO = 8080


# --------------------------------------------------------------------
# 1.1 Cliente contra netcat
# --------------------------------------------------------------------

def cliente(mudo=False):
    """Se conecta, manda una linea y (salvo --mudo) espera la respuesta."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST_CLIENTE, PUERTO))       # handshake de tres vias
        # La cuadrupla completa recien existe despues del connect().
        print(f'Local:  {s.getsockname()}')
        print(f'Remoto: {s.getpeername()}')
        s.sendall(b'hola desde Python\n')
        if mudo:
            # Punto 3: sin recv() el cliente cierra enseguida. El servidor
            # igual recibio los bytes: sendall() ya los entrego al kernel.
            print('Enviado sin leer respuesta; cierro.')
            return
        print(f'Recibido: {s.recv(4096)!r}')


# --------------------------------------------------------------------
# 1.2 Servidor contra netcat
# --------------------------------------------------------------------

def servidor(loop=False, reuse=True):
    """Servidor de una sola conexion, o de a una por vez si loop=True."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        if reuse:
            # SIEMPRE antes del bind(); despues no tiene efecto.
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((HOST_SERVIDOR, PUERTO))
        except OSError as e:
            # Esto es lo que se ve en el punto 6 al relanzar sin SO_REUSEADDR.
            print(f'bind() fallo: {e}')
            print('El puerto sigue tomado por una conexion en TIME_WAIT.')
            print('Verlo con:  ss -tan state time-wait | head     (Linux)')
            print('            netstat -an | findstr TIME_WAIT    (Windows)')
            return
        srv.listen(5)
        print(f'Escuchando en {HOST_SERVIDOR}:{PUERTO} '
              f'(SO_REUSEADDR {"ON" if reuse else "OFF"}). Ctrl+C para salir.')

        while True:
            # accept() devuelve un socket NUEVO: `srv` sigue escuchando y
            # nunca transmite datos de aplicacion.
            conn, dir = srv.accept()
            with conn:
                print(f'Conexion desde {dir}')            # (IP, puerto) del cliente
                print(f'  socket que escucha: {srv.getsockname()} (sin peer)')
                print(f'  socket de la conv.: {conn.getsockname()} <-> '
                      f'{conn.getpeername()}')
                datos = conn.recv(4096)
                conn.sendall(b'ECHO: ' + datos)
            if not loop:
                # Punto 5: sin el while, el servidor muere tras un cliente.
                print('Atendi una conexion y termino (sin --loop).')
                return


# --------------------------------------------------------------------
# Demo autocontenida: servidor en un hilo, cliente en el principal
# --------------------------------------------------------------------

def demo():
    hilo = threading.Thread(target=servidor, daemon=True)
    hilo.start()
    time.sleep(0.3)                     # dejar que llegue al accept()
    print('--- cliente ---')
    cliente()
    hilo.join(timeout=2)


if __name__ == '__main__':
    args = sys.argv[1:]
    try:
        if '--servidor' in args:
            servidor(loop='--loop' in args, reuse='--sin-reuse' not in args)
        elif '--cliente' in args:
            cliente(mudo='--mudo' in args)
        else:
            demo()
    except KeyboardInterrupt:
        print('\nCortado')
    except ConnectionRefusedError:
        print(f'No hay nadie escuchando en {HOST_CLIENTE}:{PUERTO}.')
        print('Levanta:  python3 ejercicio1.py --servidor   (o nc -l 8080)')


"""
Preguntas y respuestas
======================

1.1 Cliente contra netcat
-------------------------
1. Corre el cliente. Aparece el mensaje en la terminal del nc?
   Si. `nc -l 8080` imprime en pantalla todo lo que le llega, asi que se ve
   "hola desde Python" apenas el cliente hace sendall(). El cliente queda
   bloqueado en recv() esperando respuesta.

2. Que imprime el cliente cuando escribo algo en el nc y presiono Enter?
   Imprime `Recibido: b'lo que escribi\\n'`. El \\n viene del Enter: nc manda
   la linea entera, salto incluido. Hasta ese momento recv() estaba bloqueado,
   sin consumir CPU: bloquear no es esperar activamente.

3. Si saco el recv(), nota la diferencia el servidor?
   No, o casi. sendall() ya entrego los bytes al kernel y el kernel ya los
   transmitio; nc los muestra igual. Lo unico que cambia es que el cliente
   cierra de inmediato y nc ve el FIN (fin de entrada). Si nc intenta escribir
   despues de eso, ahi si falla, pero el mensaje original llego igual.
   Moraleja: recv() es cosa del que lee, no una confirmacion de envio.

1.2 Servidor contra netcat
--------------------------
4. Que imprime `dir`? Relacionalo con la cuadrupla de la clase 12.
   Una tupla (IP, puerto) del CLIENTE, por ejemplo ('127.0.0.1', 54321). El
   puerto es efimero, lo asigna el kernel del cliente al hacer connect().
   La cuadrupla que identifica una conexion TCP es
       (IP origen, puerto origen, IP destino, puerto destino)
   El socket que escucha solo tiene definida la mitad local, ('0.0.0.0', 8080),
   y no tiene peer. Cada `conn` que devuelve accept() tiene los cuatro valores
   completos, y por eso identifica una conversacion puntual. Dos clientes desde
   la misma maquina se distinguen justamente por el puerto origen distinto.
   (En el codigo, los prints de getsockname()/getpeername() lo muestran.)

5. El servidor atiende una sola conexion y termina. Que habria que cambiar?
   Envolver accept() en un `while True`. Es lo que hace el flag --loop.
   Ojo: eso lo vuelve un servidor SECUENCIAL, atiende de a uno (ejercicio 6).

1.3 SO_REUSEADDR
----------------
6. Sin setsockopt, cortar con Ctrl+C y relanzar enseguida da:
       OSError: [Errno 98] Address already in use        (Linux)
       OSError: [WinError 10048] ...                     (Windows)
   Aunque no haya ningun proceso usando el puerto. La causa es que la conexion
   ya cerrada quedo en estado TIME_WAIT (1 a 4 minutos) para absorber paquetes
   rezagados, y el kernel considera ese par (IP, puerto) todavia en uso.
   Detalle: hace falta que haya habido una conexion aceptada antes de matar el
   servidor; si nadie se conecto nunca, no hay TIME_WAIT y el bind() anda.

7. `ss -tan state time-wait | head` muestra la conexion con puerto local 8080
   en estado TIME-WAIT. En Windows: `netstat -an | findstr TIME_WAIT`.

8. Con la linea puesta, desaparece: SO_REUSEADDR le dice al kernel que permita
   el bind() aunque haya un TIME_WAIT sobre esa direccion. Tiene que ir ANTES
   del bind(); llamarlo despues no sirve de nada.
"""
