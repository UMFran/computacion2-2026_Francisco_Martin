#!/usr/bin/env python3
"""Ejercicio 6: un servidor que hace trabajo de CPU real.

Hasta ahora el "trabajo" era un sleep, que es I/O-bound simulado y libera
el GIL. Esto no lo libera.

    python3 ejercicio6_cpu.py [puerto] --threads
    python3 ejercicio6_cpu.py [puerto] --fork

Despues:  python3 benchmark.py --clientes 10
"""
import os
import signal
import socket
import sys
import threading

HOST = '0.0.0.0'
ARGS = sys.argv[1:]
PUERTO = int(ARGS[0]) if ARGS and ARGS[0].isdigit() else 8080
FORK = '--fork' in ARGS


def trabajo_cpu(n=2_000_000):
    """CPU-bound de verdad: no libera el GIL."""
    total = 0
    for i in range(n):
        total += i * i
    return total


def atender(conn):
    trabajo_cpu()
    while True:
        datos = conn.recv(4096)
        if not datos:
            break
        conn.sendall(datos)


def cosechar(signum, frame):
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
        except ChildProcessError:
            break


def main():
    if FORK:
        signal.signal(signal.SIGCHLD, cosechar)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(128)
        print(f'[{"fork" if FORK else "threads"}] escuchando en '
              f'{HOST}:{PUERTO} (trabajo CPU-bound)', flush=True)

        while True:
            try:
                conn, _dir = servidor.accept()
            except InterruptedError:
                continue

            if FORK:
                if os.fork() == 0:
                    servidor.close()
                    try:
                        atender(conn)
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                    finally:
                        conn.close()
                        os._exit(0)
                else:
                    conn.close()
            else:
                threading.Thread(target=atender, args=(conn,),
                                 daemon=True).start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
