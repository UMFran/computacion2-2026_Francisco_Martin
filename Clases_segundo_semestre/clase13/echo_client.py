#!/usr/bin/env python3
"""Cliente del servidor eco, con demostración de lecturas parciales.

Uso:
    python3 echo_client.py                   # envía un mensaje y lo lee
    python3 echo_client.py --parcial         # lee de a 4 bytes
    python3 echo_client.py --tres            # tres sendall(): ver el framing
    python3 echo_client.py --varios [N]      # N clientes simultáneos (default 5)

Requiere echo_server.py corriendo en otra terminal. Como el servidor
demora unos segundos por solicitud, el timeout es holgado.
"""
import socket
import sys
import threading
import time

# 127.0.0.1 y no 'localhost': en Windows ese nombre resuelve primero a
# ::1 (IPv6) y el servidor escucha en IPv4, asi que cada conexion paga
# un intento fallido de ~2s antes del fallback. Falsea las mediciones.
HOST, PUERTO = '127.0.0.1', 8080
TIMEOUT = 60


def simple(etiqueta=''):
    """Un envío, una lectura."""
    prefijo = f'[{etiqueta}] ' if etiqueta else ''
    inicio = time.perf_counter()
    with socket.create_connection((HOST, PUERTO), timeout=TIMEOUT) as s:
        s.sendall(f'hola mundo {etiqueta}\n'.encode())
        respuesta = s.recv(4096)
        print(f'{prefijo}Recibido: {respuesta!r} '
              f'({time.perf_counter() - inicio:.2f}s)')


def parcial():
    """Lee de a 4 bytes para hacer visible que recv() devuelve lo que hay."""
    mensaje = b'un mensaje bastante mas largo que cuatro bytes\n'
    with socket.create_connection((HOST, PUERTO), timeout=TIMEOUT) as s:
        s.sendall(mensaje)
        s.shutdown(socket.SHUT_WR)      # "no mando más"; el server verá b''
        recibido = b''
        while True:
            pedazo = s.recv(4)          # tope de 4 bytes a propósito
            if not pedazo:
                break
            print(f'  recv(4) -> {pedazo!r}')
            recibido += pedazo
        print(f'Total: {len(recibido)} bytes de {len(mensaje)} enviados')


def tres():
    """Tres sendall() separados: el servidor casi nunca ve tres recv()."""
    with socket.create_connection((HOST, PUERTO), timeout=TIMEOUT) as s:
        for msg in (b'HOLA', b'COMO', b'ESTAS'):
            s.sendall(msg)
        time.sleep(0.5)                 # dar tiempo al eco
        print(f'Eco recibido: {s.recv(4096)!r}')
        print('Mirá la salida del servidor: ¿cuántos recv() hizo?')


def varios():
    """N clientes al mismo tiempo, cada uno en su hilo.

    Contra el servidor concurrente el total tarda ~lo que tarda uno solo.
    Contra el mismo servidor con --secuencial, tarda N veces más: ahí se
    ve que la cola de listen() sólo guarda, no atiende.
    """
    cantidad = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    hilos = [threading.Thread(target=simple, args=(f'cliente-{i + 1}',))
             for i in range(cantidad)]
    inicio = time.perf_counter()
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()                        # esperar a todos antes de medir
    print(f'{cantidad} clientes en {time.perf_counter() - inicio:.2f}s')


if __name__ == '__main__':
    modo = sys.argv[1] if len(sys.argv) > 1 else ''
    try:
        {'--parcial': parcial, '--tres': tres, '--varios': varios}.get(
            modo, simple)()
    except ConnectionRefusedError:
        print(f'No hay nadie escuchando en {HOST}:{PUERTO}.')
        print('Levantá el servidor con: python3 echo_server.py')
