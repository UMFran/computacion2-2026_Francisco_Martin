#!/usr/bin/env python3
"""Ejercicio 4: race condition real en el contador de clientes.

Copia de server_threads.py SIN el lock que protege `clientes_activos`.
Al terminar imprime el contador: si no volvio a 0, se perdieron
actualizaciones.

    python3 ejercicio4_sin_lock.py [puerto] [--dormir]

--dormir agrega un sleep entre la lectura y la escritura, que agranda la
ventana de la carrera (punto 3).

Despues correr:  python3 benchmark.py --clientes 200
y cortar el servidor con Ctrl+C para ver el contador final.
"""
import signal
import socket
import sys
import threading
import time

HOST = '0.0.0.0'
ARGS = sys.argv[1:]
PUERTO = int(ARGS[0]) if ARGS and ARGS[0].isdigit() else 8080
LENTO = float(ARGS[ARGS.index('--lento') + 1]) if '--lento' in ARGS else 0.0
DORMIR = '--dormir' in ARGS

clientes_activos = 0
pico_simultaneos = 0
atendidos = 0


def sumar(cantidad):
    """La operacion que deberia estar protegida.

    clientes_activos += 1 no es atomico: son tres pasos (leer, sumar,
    escribir) y el intercambio de hilos puede caer en el medio.
    """
    global clientes_activos
    actual = clientes_activos
    if DORMIR:
        time.sleep(0.0001)      # agranda la ventana de la carrera
    clientes_activos = actual + cantidad


def atender(conn, direccion):
    global pico_simultaneos, atendidos
    sumar(1)
    pico_simultaneos = max(pico_simultaneos, clientes_activos)
    atendidos += 1
    try:
        if LENTO:
            time.sleep(LENTO)
        with conn:
            while True:
                datos = conn.recv(4096)
                if not datos:
                    break
                conn.sendall(datos)
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        sumar(-1)


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(128)
        print(f'[sin lock] escuchando en {HOST}:{PUERTO} '
              f'(dormir={DORMIR})', flush=True)

        while True:
            conn, direccion = servidor.accept()
            threading.Thread(target=atender, args=(conn, direccion),
                             daemon=True).start()


def informar(signum=None, frame=None):
    print(f'\nAtendidos: {atendidos}')
    print(f'clientes_activos al final: {clientes_activos} (deberia ser 0)')
    print(f'Pico de simultaneos: {pico_simultaneos}', flush=True)
    sys.exit(0)


if __name__ == '__main__':
    # SIGTERM ademas de Ctrl+C, para poder medirlo desde un script.
    signal.signal(signal.SIGTERM, informar)
    try:
        main()
    except KeyboardInterrupt:
        informar()
