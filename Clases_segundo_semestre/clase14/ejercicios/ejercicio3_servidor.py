#!/usr/bin/env python3
"""Ejercicio 3 (OBLIGATORIO): los tres descuidos del fork.

Copia de server_fork.py con los descuidos activables por bandera, para no
tener cuatro archivos casi iguales.

    python3 ejercicio3_servidor.py --sin-cierre-padre     # Parte A
    python3 ejercicio3_servidor.py --guardar-conexiones   # Parte A2
    python3 ejercicio3_servidor.py --sin-cosechar         # Parte B
    python3 ejercicio3_servidor.py --sig-ign              # Parte D
    python3 ejercicio3_servidor.py                        # correcto

Solo Unix (usa fork). Correr desde WSL.
"""
import os
import signal
import socket
import sys
import time

HOST = '0.0.0.0'
ARGS = sys.argv[1:]
PUERTO = int(ARGS[0]) if ARGS and ARGS[0].isdigit() else 8080
LENTO = float(ARGS[ARGS.index('--lento') + 1]) if '--lento' in ARGS else 0.0

SIN_CIERRE_PADRE = '--sin-cierre-padre' in ARGS
GUARDAR_CONEXIONES = '--guardar-conexiones' in ARGS
SIN_COSECHAR = '--sin-cosechar' in ARGS
SIG_IGN = '--sig-ign' in ARGS

conexiones_abiertas = []        # Parte A2: referencias que sobreviven


def cosechar(signum, frame):
    """Recoge hijos terminados sin bloquear."""
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
        except ChildProcessError:
            break


def atender(conn):
    if LENTO:
        time.sleep(LENTO)
    while True:
        datos = conn.recv(4096)
        if not datos:
            break
        conn.sendall(datos)


def main():
    if SIG_IGN:
        # Parte D: delegarle la cosecha al kernel.
        signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    elif not SIN_COSECHAR:
        signal.signal(signal.SIGCHLD, cosechar)
    # con --sin-cosechar no se instala nada: aparecen zombies

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((HOST, PUERTO))
        servidor.listen(128)
        print(f'[fork] PADRE pid={os.getpid()} escuchando en {HOST}:{PUERTO}')
        print(f'       sin_cierre_padre={SIN_CIERRE_PADRE} '
              f'guardar={GUARDAR_CONEXIONES} sin_cosechar={SIN_COSECHAR} '
              f'sig_ign={SIG_IGN}', flush=True)

        while True:
            try:
                conn, direccion = servidor.accept()
            except InterruptedError:
                continue

            pid = os.fork()

            if pid == 0:
                # ---- HIJO ----
                servidor.close()
                try:
                    atender(conn)
                except (ConnectionResetError, BrokenPipeError):
                    pass
                finally:
                    conn.close()
                    os._exit(0)
            else:
                # ---- PADRE ----
                if GUARDAR_CONEXIONES:
                    conexiones_abiertas.append(conn)    # la referencia sobrevive
                elif not SIN_CIERRE_PADRE:
                    conn.close()
                # con --sin-cierre-padre no se cierra ni se guarda:
                # el recolector de CPython lo cierra igual al reasignar `conn`


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nServidor detenido')
