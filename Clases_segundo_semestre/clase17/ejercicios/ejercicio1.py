#!/usr/bin/env python3
"""Ejercicio 1.1: servidor con polling activo. Funciona, pero mal.

Atiende varios clientes con sockets no bloqueantes, SIN usar select().
Mirar el consumo de CPU con top/htop mientras no hay nadie conectado.

    python3 ejercicio1.py
    nc localhost 8080
"""
import socket

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('localhost', 8080))
srv.listen(5)
srv.setblocking(False)

print('Escuchando en localhost:8080 con polling activo (Ctrl+C para salir)')
print('Mira el CPU con top: gira al 100% aunque no haya nadie conectado.')

conexiones = []
try:
    while True:
        try:
            conn, _ = srv.accept()
            conn.setblocking(False)
            conexiones.append(conn)
        except BlockingIOError:
            pass
        for c in list(conexiones):
            try:
                datos = c.recv(4096)
                if datos:
                    c.sendall(datos)
                else:
                    conexiones.remove(c)
                    c.close()
            except BlockingIOError:
                pass
except KeyboardInterrupt:
    print('\nServidor detenido')
finally:
    for c in conexiones:
        c.close()
    srv.close()
