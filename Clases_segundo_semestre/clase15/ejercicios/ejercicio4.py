#!/usr/bin/env python3
"""Ejercicio 4: connect() en UDP.

Compara el mismo envio a un puerto vacio con y sin connect().
"""
import socket

PUERTO_VACIO = 9999


def con_connect():
    print('--- con connect() ---')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    s.connect(('localhost', PUERTO_VACIO))     # puerto donde no hay nadie
    s.send(b'hola')
    try:
        s.recv(4096)
        print('  llego una respuesta (inesperado)')
    except ConnectionRefusedError:
        print('  ConnectionRefusedError  (lo que da Linux)')
    except ConnectionResetError:
        print('  ConnectionResetError    (lo que da Windows)')
    except TimeoutError:
        print('  timeout')
    s.close()


def sin_connect():
    print('--- sin connect(), con sendto/recvfrom ---')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2)
    s.sendto(b'hola', ('localhost', PUERTO_VACIO))
    try:
        s.recvfrom(4096)
        print('  llego una respuesta (inesperado)')
    except ConnectionRefusedError:
        print('  ConnectionRefusedError')
    except ConnectionResetError:
        print('  ConnectionResetError')
    except TimeoutError:
        print('  timeout (nadie avisa nada)')
    s.close()


if __name__ == '__main__':
    con_connect()
    sin_connect()
