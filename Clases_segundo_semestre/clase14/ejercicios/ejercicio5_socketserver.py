#!/usr/bin/env python3
"""Ejercicio 5: el servidor eco con socketserver.

Lo mismo que server_threads.py, en una fraccion del codigo.

    python3 ejercicio5_socketserver.py [puerto] [--lento SEGUNDOS] [--fork]

--fork usa ForkingTCPServer en vez de ThreadingTCPServer (punto 3).
"""
import socketserver
import sys
import time

ARGS = sys.argv[1:]
PUERTO = int(ARGS[0]) if ARGS and ARGS[0].isdigit() else 8080
LENTO = float(ARGS[ARGS.index('--lento') + 1]) if '--lento' in ARGS else 0.0
FORK = '--fork' in ARGS


class EchoHandler(socketserver.StreamRequestHandler):
    def handle(self):
        if LENTO:
            time.sleep(LENTO)
        # rfile/wfile son objetos tipo archivo sobre el socket. Iterando
        # "for linea in self.rfile" se tendria el framing por lineas gratis,
        # pero benchmark.py manda 256 bytes SIN \n y quedaria esperando un
        # salto que no llega. read1() devuelve lo que haya, como recv().
        while True:
            datos = self.rfile.read1(4096)
            if not datos:
                break
            self.wfile.write(datos)


class ServidorThreads(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ServidorFork(socketserver.ForkingTCPServer):
    allow_reuse_address = True


if __name__ == '__main__':
    Servidor = ServidorFork if FORK else ServidorThreads
    with Servidor(('0.0.0.0', PUERTO), EchoHandler) as srv:
        print(f'[{Servidor.__name__}] escuchando en 0.0.0.0:{PUERTO}'
              f'{f" (lento: {LENTO}s)" if LENTO else ""}', flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print('\nServidor detenido')
