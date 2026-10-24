#!/usr/bin/env python3
"""Servidor eco TCP concurrente (un hilo por cliente).

Cada conexión aceptada se despacha a un hilo propio, así que N clientes
se atienden a la vez. Para hacer visible la diferencia, el servidor
simula trabajo pesado: duerme unos segundos antes de responder cada
solicitud.

Con --secuencial vuelve al comportamiento de la clase 13 (un cliente a
la vez): útil para comparar los tiempos con el mismo cliente.

Uso:
    python3 echo_server.py [puerto] [--secuencial] [--demora SEGUNDOS]

Probalo con echo_client.py --varios 5, o con:
    nc localhost 8080
"""
import socket
import sys
import threading
import time

HOST = '0.0.0.0'

ARGS = sys.argv[1:]
SECUENCIAL = '--secuencial' in ARGS
if '--demora' in ARGS:
    i = ARGS.index('--demora')
    DEMORA = float(ARGS[i + 1])
    ARGS = ARGS[:i] + ARGS[i + 2:]      # saco la opción y su valor
else:
    DEMORA = 3.0
POSICIONALES = [a for a in ARGS if not a.startswith('--')]
PUERTO = int(POSICIONALES[0]) if POSICIONALES else 8080


def atender(conn, direccion):
    """Devuelve todo lo que el cliente mande, hasta que cierre."""
    etiqueta = f'{threading.current_thread().name} {direccion[0]}:{direccion[1]}'
    total = 0
    while True:
        datos = conn.recv(4096)
        if not datos:
            # recv() vacío = el otro lado cerró. Sin este chequeo,
            # el bucle giraría infinitamente consumiendo CPU.
            break
        total += len(datos)
        print(f'  [{etiqueta}] recv {len(datos)} bytes: {datos!r}')
        # Trabajo simulado: acá iría una consulta a disco, a una base,
        # o cualquier cosa lenta. Mientras este hilo duerme, los demás
        # hilos siguen atendiendo a sus propios clientes.
        print(f'  [{etiqueta}] procesando {DEMORA}s...')
        time.sleep(DEMORA)
        conn.sendall(datos)
    print(f'  [{etiqueta}] cerró tras {total} bytes')


def atender_seguro(conn, direccion):
    """Envoltorio del hilo: una excepción acá no debe tumbar el servidor."""
    try:
        with conn:
            atender(conn, direccion)
    except (ConnectionResetError, BrokenPipeError, OSError) as e:
        # Un cliente que corta mal sólo se lleva puesto su propio hilo.
        print(f'  [{direccion}] desconexión abrupta: {e}')


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        # Antes del bind: permite reusar el puerto aunque haya
        # conexiones en TIME_WAIT de una ejecución anterior.
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(1) #cola de clientes
        modo = 'SECUENCIAL' if SECUENCIAL else 'CONCURRENTE (un hilo por cliente)'
        print(f'Escuchando en {HOST}:{PUERTO} - modo {modo}, demora {DEMORA}s')
        print('(Ctrl+C para salir)')

        while True:
            # accept() devuelve un socket NUEVO. `servidor` sigue escuchando
            # y nunca transmite datos de aplicación.
            conn, direccion = servidor.accept()
            print(f'Conexión desde {direccion}')
            if SECUENCIAL:
                atender_seguro(conn, direccion)
            else:
                # daemon=True: los hilos no impiden que el proceso termine
                # con Ctrl+C. accept() vuelve a girar de inmediato.
                threading.Thread(
                    target=atender_seguro,
                    args=(conn, direccion),
                    daemon=True,
                ).start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
