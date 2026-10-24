#!/usr/bin/env python3
"""Ejercicio 6: chat multiusuario con /nick, /lista y framing arreglado.

Sobre chat.py se agregan tres cosas:
  - punto 3: comando /nick <nombre>
  - punto 4: comando /lista
  - punto 6: buffer por cliente, para no asumir que cada recv() trae
    una linea completa (puntos 5 y 6)

    python3 ejercicio6.py [puerto]
    nc localhost 8080        (desde varias terminales)
"""
import selectors
import socket
import sys

PUERTO = int(sys.argv[1]) if len(sys.argv) > 1 else 8080

sel = selectors.DefaultSelector()
clientes = {}           # socket -> apodo
salida = {}             # socket -> bytes pendientes de enviar
entrada = {}            # socket -> bytes recibidos sin procesar (framing)


def difundir(mensaje: bytes, excepto=None):
    """Encola un mensaje para todos los clientes menos uno."""
    for conn in clientes:
        if conn is excepto:
            continue
        salida[conn] = salida.get(conn, b'') + mensaje
        sel.modify(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, manejar)


def encolar(conn, mensaje: bytes):
    """Encola un mensaje para un solo cliente."""
    salida[conn] = salida.get(conn, b'') + mensaje
    sel.modify(conn, selectors.EVENT_READ | selectors.EVENT_WRITE, manejar)


def aceptar(servidor, _mascara):
    conn, direccion = servidor.accept()
    conn.setblocking(False)
    apodo = f'{direccion[0]}:{direccion[1]}'
    clientes[conn] = apodo
    entrada[conn] = b''
    sel.register(conn, selectors.EVENT_READ, manejar)
    print(f'+ {apodo}  ({len(clientes)} conectados)')
    encolar(conn, b'Bienvenido al chat. /nick <nombre>, /lista\n')
    difundir(f'* se conecto {apodo}\n'.encode(), excepto=conn)


def desconectar(conn):
    apodo = clientes.pop(conn, '?')
    salida.pop(conn, None)
    entrada.pop(conn, None)
    sel.unregister(conn)            # SIEMPRE antes de close()
    conn.close()
    print(f'- {apodo}  ({len(clientes)} conectados)')
    difundir(f'* se fue {apodo}\n'.encode())


def procesar_linea(conn, texto):
    """Una linea COMPLETA de un cliente: comando o mensaje."""
    apodo = clientes.get(conn, '?')

    if texto.startswith('/nick '):
        nuevo = texto[6:].strip()
        if not nuevo:
            encolar(conn, b'* /nick necesita un nombre\n')
            return
        clientes[conn] = nuevo
        encolar(conn, f'* ahora sos {nuevo}\n'.encode())
        difundir(f'* {apodo} ahora se llama {nuevo}\n'.encode(), excepto=conn)
        print(f'  {apodo} -> {nuevo}')
        return

    if texto == '/lista':
        nombres = ', '.join(clientes.values())
        encolar(conn, f'* conectados ({len(clientes)}): {nombres}\n'.encode())
        return

    if texto:
        print(f'  <{apodo}> {texto}')
        difundir(f'<{apodo}> {texto}\n'.encode(), excepto=conn)


def manejar(conn, mascara):
    """Un solo handler para lectura y escritura."""
    if mascara & selectors.EVENT_READ:
        try:
            datos = conn.recv(4096)
        except ConnectionResetError:
            desconectar(conn)
            return
        if not datos:
            desconectar(conn)
            return

        # FRAMING (puntos 5 y 6): un recv() puede traer media linea, o dos
        # lineas y media. El buffer acumula entre llamadas y solo se
        # procesan las lineas COMPLETAS, igual que en framing.py (clase 13).
        entrada[conn] = entrada.get(conn, b'') + datos
        while b'\n' in entrada[conn]:
            linea, entrada[conn] = entrada[conn].split(b'\n', 1)
            texto = linea.decode('utf-8', errors='replace').rstrip('\r')
            procesar_linea(conn, texto)
            if conn not in clientes:        # se desconecto en el camino
                return

    if mascara & selectors.EVENT_WRITE:
        buf = salida.get(conn, b'')
        if buf:
            try:
                n = conn.send(buf)
            except (BrokenPipeError, ConnectionResetError):
                desconectar(conn)
                return
            salida[conn] = buf[n:]
        if not salida.get(conn) and conn in clientes:
            sel.modify(conn, selectors.EVENT_READ, manejar)


def main():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('0.0.0.0', PUERTO))
    servidor.listen(128)
    servidor.setblocking(False)
    sel.register(servidor, selectors.EVENT_READ, aceptar)

    print(f'Chat escuchando en 0.0.0.0:{PUERTO} ({type(sel).__name__})')
    print('Conectate con: nc localhost', PUERTO)

    try:
        while True:
            for clave, mascara in sel.select():
                clave.data(clave.fileobj, mascara)
    except KeyboardInterrupt:
        print('\nChat detenido')
    finally:
        sel.close()


if __name__ == '__main__':
    main()
