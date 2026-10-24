#!/usr/bin/env python3
"""Ejercicio 6: Fragmentación y MTU.

Manda datagramas de distinto tamaño a un servidor local y cuenta cuántos
llegan completos.

    python3 ejercicio6.py              # 60000 y 1000 bytes, 20 envios cada uno
"""
import socket
import threading
import time

HOST = '127.0.0.1'
PUERTO = 8083
REPETICIONES = 20


def servidor(recibidos, parar):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    s.bind((HOST, PUERTO))
    s.settimeout(0.3)
    while not parar.is_set():
        try:
            datos, _ = s.recvfrom(65535)
        except TimeoutError:
            continue
        recibidos.append(len(datos))
    s.close()


def probar(tamanio):
    recibidos = []
    parar = threading.Event()
    hilo = threading.Thread(target=servidor, args=(recibidos, parar),
                            daemon=True)
    hilo.start()
    time.sleep(0.3)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    enviados = 0
    for _ in range(REPETICIONES):
        try:
            s.sendto(b'X' * tamanio, (HOST, PUERTO))
            enviados += 1
        except OSError as e:
            print(f"  sendto fallo: {e}")
            break
        time.sleep(0.02)
    s.close()
    time.sleep(0.5)
    parar.set()
    hilo.join(timeout=2)

    completos = sum(1 for n in recibidos if n == tamanio)
    print(f"  {tamanio:6} bytes: enviados {enviados}, "
          f"recibidos {len(recibidos)}, completos {completos}")
    return completos, enviados


if __name__ == '__main__':
    # Punto 1 y 2: MTU y cuanto payload entra sin fragmentar.
    mtu = 1500          # valor tipico de Ethernet; verificar con: ip link show
    print(f"MTU tipico de Ethernet: {mtu}")
    print(f"Payload UDP sin fragmentar: {mtu} - 20 (IP) - 8 (UDP) = "
          f"{mtu - 28} bytes")
    print(f"Un datagrama de 60000 bytes se parte en "
          f"~{-(-60000 // (mtu - 28))} fragmentos IP\n")

    print("Punto 3 y 4: envios a un servidor local")
    probar(60000)
    probar(1000)
