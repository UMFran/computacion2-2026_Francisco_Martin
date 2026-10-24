#!/usr/bin/env python3
"""Ejercicio 2.2: el buffer chico trunca el datagrama.

OJO con la diferencia de plataforma:
  Linux   -> recvfrom(10) TRUNCA en silencio y descarta el resto.
  Windows -> lanza OSError WSAEMSGSIZE (WinError 10040).
En los dos casos los 90 bytes restantes se pierden; lo que cambia es si
el sistema avisa o no.
"""
import socket

r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
r.bind(('localhost', 8081))

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.sendto(b'X' * 100, ('localhost', 8081))

try:
    datos, _ = r.recvfrom(10)      # buffer de 10 para un datagrama de 100
    print(f'primer recvfrom: {len(datos)} bytes (trunco en silencio)')
except OSError as e:
    print(f'primer recvfrom: OSError {e.winerror if hasattr(e, "winerror") else e.errno}')
    print(f'  {e.strerror}')

r.settimeout(1.0)
try:
    datos2, _ = r.recvfrom(65535)
    print(f'segundo recvfrom: {len(datos2)} bytes')
except TimeoutError:
    print('segundo recvfrom: nada')
except OSError as e:
    print(f'segundo recvfrom: OSError {e.strerror}')

r.close()
s.close()
