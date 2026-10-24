#!/usr/bin/env python3
"""Clase 16: importar socketserver, crear el objeto e imprimir su tipo."""
import socketserver

class MiHandler(socketserver.BaseRequestHandler):
    def handle(self):
        datos = self.request.recv(4096)      # self.request ES el socket
        self.request.sendall(datos.upper())


servidor = socketserver.TCPServer(('localhost', 8080), MiHandler)
print(type(servidor))
servidor.server_close()
