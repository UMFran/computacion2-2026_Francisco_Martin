#!/usr/bin/env python3
"""Ejercicio 5: Broadcast.

    python3 ejercicio5.py --servidor     # responde DISCOVER? con su hostname
    python3 ejercicio5.py --cliente      # manda DISCOVER? al broadcast
    python3 ejercicio5.py --sin-opcion   # punto 1: sin SO_BROADCAST
    python3 ejercicio5.py                # servidor y cliente juntos
"""
import socket
import sys
import threading
import time

PUERTO = 8082


def servidor():
    """Punto 2: responde al DISCOVER? con el nombre de la maquina."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', PUERTO))            # '' = todas las interfaces
    s.settimeout(5)
    print(f'[servidor] escuchando broadcast en :{PUERTO}', flush=True)
    try:
        while True:
            datos, origen = s.recvfrom(4096)
            if datos.strip() == b'DISCOVER?':
                respuesta = socket.gethostname().encode()
                s.sendto(respuesta, origen)
                print(f'[servidor] respondi a {origen}', flush=True)
    except TimeoutError:
        print('[servidor] fin', flush=True)
    finally:
        s.close()


def cliente(con_opcion=True):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if con_opcion:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(2.0)
    try:
        s.sendto(b'DISCOVER?', ('255.255.255.255', PUERTO))
    except OSError as e:
        # Punto 1: sin SO_BROADCAST el kernel rechaza el envio.
        print(f'[cliente] {type(e).__name__}: {e}')
        s.close()
        return
    try:
        datos, origen = s.recvfrom(4096)
        print(f'[cliente] {origen} respondió: {datos!r}')
    except TimeoutError:
        print('[cliente] Nadie respondió')
    s.close()


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--servidor' in args:
        servidor()
    elif '--cliente' in args:
        cliente()
    elif '--sin-opcion' in args:
        cliente(con_opcion=False)
    else:
        threading.Thread(target=servidor, daemon=True).start()
        time.sleep(0.5)
        print('--- con SO_BROADCAST ---')
        cliente(con_opcion=True)
        print('--- sin SO_BROADCAST ---')
        cliente(con_opcion=False)
