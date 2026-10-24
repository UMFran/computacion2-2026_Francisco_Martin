#!/usr/bin/env python3
"""Ejercicio 4: servidor_select.py reescrito con selectors.

Lo que desaparece respecto de la version con select():
  - la lista `vigilados` (el selector lleva el registro adentro)
  - el diccionario `direcciones` (va como `data` en register())
  - el `if sock is servidor` (cada socket trae su propio handler)

    python3 ejercicio4.py [puerto] [--select]

--select fuerza SelectSelector en vez del default (punto 3).
"""
import selectors
import socket
import sys

ARGS = sys.argv[1:]
PUERTO = int(ARGS[0]) if ARGS and ARGS[0].isdigit() else 8080
USAR_SELECT = '--select' in ARGS

sel = selectors.SelectSelector() if USAR_SELECT else selectors.DefaultSelector()


def aceptar(servidor, _mascara):
    conn, direccion = servidor.accept()
    conn.setblocking(False)
    # La direccion viaja como `data`: no hace falta el diccionario aparte.
    sel.register(conn, selectors.EVENT_READ, (atender, direccion))
    print(f'+ cliente {direccion}')


def atender(conn, _mascara, direccion):
    datos = conn.recv(4096)
    if datos:
        conn.sendall(datos)
    else:
        # unregister() SIEMPRE antes de close(): el selector trabaja con
        # el numero de fd, y si el fd ya esta cerrado no puede sacarlo.
        sel.unregister(conn)
        conn.close()
        print(f'- cliente {direccion}')


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('0.0.0.0', PUERTO))
    servidor.listen(128)
    servidor.setblocking(False)
    sel.register(servidor, selectors.EVENT_READ, (aceptar, None))

    print(f'Escuchando en 0.0.0.0:{PUERTO} con {type(sel).__name__}')

    try:
        while True:
            for clave, mascara in sel.select():
                handler, direccion = clave.data
                if direccion is None:
                    handler(clave.fileobj, mascara)
                else:
                    handler(clave.fileobj, mascara, direccion)
    except KeyboardInterrupt:
        print('\nServidor detenido')
    finally:
        sel.close()


if __name__ == '__main__':
    main()
