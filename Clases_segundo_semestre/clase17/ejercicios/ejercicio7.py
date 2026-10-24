#!/usr/bin/env python3
"""Ejercicio 7: el costo del hilo unico.

Servidor con selectors y un handler que hace trabajo PESADO de CPU.
Mientras procesa al primer cliente, el segundo no recibe nada.

    python3 ejercicio7.py [puerto]

Despues, desde dos terminales:
    nc localhost 8080        (escribir algo: tarda ~2s)
    nc localhost 8080        (escribir algo mientras el otro procesa)
"""
import hashlib
import selectors
import socket
import sys
import time

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

sel = selectors.DefaultSelector()


def aceptar(servidor, _mascara):
    conn, direccion = servidor.accept()
    conn.setblocking(False)
    sel.register(conn, selectors.EVENT_READ, atender)
    print(f'+ cliente {direccion}', flush=True)


def atender(conn, _mascara):
    datos = conn.recv(4096)
    if datos:
        inicio = time.perf_counter()
        h = datos
        for _ in range(3_000_000):        # ~2 segundos de CPU
            h = hashlib.sha256(h).digest()
        print(f'  procesado en {time.perf_counter() - inicio:.1f}s', flush=True)
        conn.sendall(h.hex().encode() + b'\n')
    else:
        sel.unregister(conn)
        conn.close()
        print('- cliente', flush=True)


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('0.0.0.0', PUERTO))
    servidor.listen(128)
    servidor.setblocking(False)
    sel.register(servidor, selectors.EVENT_READ, aceptar)
    print(f'Escuchando en 0.0.0.0:{PUERTO} (un hilo, trabajo CPU-bound)')

    try:
        while True:
            for clave, mascara in sel.select():
                clave.data(clave.fileobj, mascara)
    except KeyboardInterrupt:
        print('\nServidor detenido')
    finally:
        sel.close()


if __name__ == '__main__':
    main()
