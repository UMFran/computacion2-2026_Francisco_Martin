#!/usr/bin/env python3
import os
import signal
import socketserver
import threading
import time
from datetime import datetime

class FechaUDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = self.request[0].strip()
        sock = self.request[1]
        print(f"{self.client_address[0]} wrote: {data} [pid {os.getpid()}]")

        comando = data.decode("utf-8", errors="replace").lower()

        if comando == "get":
            respuesta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            respuesta = f"comando desconocido: {comando!r} (se espera 'get')"

        sock.sendto(respuesta.encode("utf-8"), self.client_address)

class ServidorFecha(socketserver.ForkingUDPServer):
    allow_reuse_address = True      # el setsockopt(SO_REUSEADDR, 1) a mano
    max_children = 40               # tope de procesos simultaneos (default 40)

parar = threading.Event()

def manejador_senial(signum, frame):
    print(f"\nSenial {signal.Signals(signum).name} recibida, cerrando...")
    parar.set()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, manejador_senial)      # Ctrl+C
    signal.signal(signal.SIGTERM, manejador_senial)     # kill


    HOST, PORT = "localhost", 9999
    with ServidorFecha((HOST, PORT), FechaUDPHandler) as server:

        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        print("Server loop running in thread:", server_thread.name)
        print(f"Escuchando en {HOST}:{PORT} (pid padre {os.getpid()}) - Ctrl+C para salir")

        while not parar.is_set():
            time.sleep(0.5)

        server.shutdown()           # hace que serve_forever() vuelva
        server_thread.join()
    print("Servidor cerrado")
