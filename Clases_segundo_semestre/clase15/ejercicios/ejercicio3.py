#!/usr/bin/env python3
"""Ejercicio 3 (OBLIGATORIO): protocolo confiable sobre UDP.

Las tres partes, cada una mostrando el problema que resuelve la siguiente:

    python3 ejercicio3.py --b          # Parte B: solo retransmision
    python3 ejercicio3.py --c          # Parte C: el servidor trabaja de mas
    python3 ejercicio3.py --d          # Parte D: numeros de secuencia
    python3 ejercicio3.py              # las tres
    python3 ejercicio3.py --d --perdida 0.7

Cliente y servidor corren adentro del mismo proceso, en hilos distintos,
con perdidas simuladas (igual que perdidas.py y confiable.py).
"""
import random
import socket
import struct
import sys
import threading
import time

HOST = '127.0.0.1'
PUERTO = 8099
MENSAJES = [b'uno', b'dos', b'tres', b'cuatro', b'cinco']


# ---------------------------------------------------------------
# Protocolo: [4 bytes de secuencia][payload]
# ---------------------------------------------------------------

def empaquetar(seq, payload):
    return struct.pack('!I', seq) + payload      # '!' = orden de red


def desempaquetar(datos):
    (seq,) = struct.unpack('!I', datos[:4])
    return seq, datos[4:]


def enviar_con_perdida(sock, datos, destino, perdida):
    """Manda, salvo que la 'red' decida descartarlo."""
    if random.random() < perdida:
        return False            # el datagrama se pierde en silencio
    sock.sendto(datos, destino)
    return True


# ---------------------------------------------------------------
# Parte B: cliente con reintentos
# ---------------------------------------------------------------

def pedir_con_reintentos(sock, mensaje, destino, intentos=5, timeout=0.5,
                         perdida=0.0):
    """Manda y reintenta si no llega respuesta.

    Devuelve (respuesta, intentos_usados) o (None, intentos) si se agotaron.
    """
    sock.settimeout(timeout)
    for intento in range(1, intentos + 1):
        enviar_con_perdida(sock, mensaje, destino, perdida)
        try:
            respuesta, _ = sock.recvfrom(65535)
            return respuesta, intento
        except TimeoutError:
            continue            # se perdio el pedido o la respuesta
    return None, intentos


# ---------------------------------------------------------------
# Servidores
# ---------------------------------------------------------------

class Servidor:
    """Servidor eco que cuenta cuantas veces hace el trabajo real.

    Con dedup=True guarda las respuestas ya calculadas y reenvia la
    guardada si llega un seq repetido.
    """

    def __init__(self, puerto, perdida=0.0, dedup=False, con_seq=True):
        self.puerto = puerto
        self.perdida = perdida
        self.dedup = dedup
        self.con_seq = con_seq
        self.trabajos = 0           # veces que ejecuto el trabajo real
        self.recibidos = 0          # datagramas que le llegaron
        self.vistos = {}            # seq -> respuesta ya calculada
        self.parar = threading.Event()

    def trabajo_real(self, payload):
        self.trabajos += 1
        return payload.upper()

    def correr(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((HOST, self.puerto))
        sock.settimeout(0.3)
        while not self.parar.is_set():
            try:
                datos, origen = sock.recvfrom(65535)
            except TimeoutError:
                continue
            self.recibidos += 1

            if not self.con_seq:
                # Parte C: sin numero de secuencia no hay forma de saber
                # si este pedido ya se atendio.
                respuesta = self.trabajo_real(datos)
                enviar_con_perdida(sock, respuesta, origen, self.perdida)
                continue

            seq, payload = desempaquetar(datos)
            if self.dedup and seq in self.vistos:
                # Duplicado: reenviar lo guardado SIN rehacer el trabajo.
                respuesta = self.vistos[seq]
            else:
                respuesta = empaquetar(seq, self.trabajo_real(payload))
                self.vistos[seq] = respuesta
            enviar_con_perdida(sock, respuesta, origen, self.perdida)
        sock.close()


def levantar(servidor):
    hilo = threading.Thread(target=servidor.correr, daemon=True)
    hilo.start()
    time.sleep(0.3)
    return hilo


# ---------------------------------------------------------------
# Parte B
# ---------------------------------------------------------------

def parte_b(perdida):
    print(f"=== Parte B: retransmision (perdida {perdida:.0%}) ===")
    srv = Servidor(PUERTO, perdida=perdida, con_seq=False)
    levantar(srv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    total_intentos = 0
    perdidos = 0
    for m in MENSAJES:
        resp, intentos = pedir_con_reintentos(
            sock, m, (HOST, PUERTO), intentos=10, timeout=0.3, perdida=perdida)
        total_intentos += intentos
        estado = resp.decode() if resp else "SIN RESPUESTA"
        if resp is None:
            perdidos += 1
        print(f"  {m.decode():8} -> {estado:12} ({intentos} intento/s)")
    sock.close()
    srv.parar.set()
    print(f"  promedio de intentos: {total_intentos / len(MENSAJES):.1f}")
    print(f"  sin respuesta: {perdidos}/{len(MENSAJES)}\n")


# ---------------------------------------------------------------
# Parte C: el duplicado
# ---------------------------------------------------------------

def parte_c(perdida):
    print(f"=== Parte C: el servidor trabaja de mas (perdida {perdida:.0%}) ===")
    srv = Servidor(PUERTO + 1, perdida=perdida, con_seq=False)
    levantar(srv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for m in MENSAJES:
        pedir_con_reintentos(sock, m, (HOST, PUERTO + 1),
                             intentos=10, timeout=0.3, perdida=perdida)
    sock.close()
    time.sleep(0.3)
    srv.parar.set()
    print(f"  mensajes distintos que mando el cliente: {len(MENSAJES)}")
    print(f"  datagramas que recibio el servidor:      {srv.recibidos}")
    print(f"  veces que hizo el TRABAJO REAL:          {srv.trabajos}")
    if srv.trabajos > len(MENSAJES):
        print(f"  -> ejecuto {srv.trabajos - len(MENSAJES)} veces de mas\n")
    else:
        print("  -> esta vez no hubo duplicados (probar con mas perdida)\n")


# ---------------------------------------------------------------
# Parte D: numeros de secuencia
# ---------------------------------------------------------------

def cliente_con_seq(sock, seq, payload, destino, intentos=10, timeout=0.3,
                    perdida=0.0):
    """Reintenta, y descarta respuestas cuyo seq no sea el del pedido actual."""
    sock.settimeout(timeout)
    pedido = empaquetar(seq, payload)
    for intento in range(1, intentos + 1):
        enviar_con_perdida(sock, pedido, destino, perdida)
        fin = time.perf_counter() + timeout
        while time.perf_counter() < fin:
            try:
                datos, _ = sock.recvfrom(65535)
            except TimeoutError:
                break
            rseq, rpayload = desempaquetar(datos)
            if rseq == seq:
                return rpayload, intento
            # respuesta demorada de un pedido anterior: descartarla
        # se acabo el tiempo de este intento
    return None, intentos


def parte_d(perdida):
    print(f"=== Parte D: numeros de secuencia (perdida {perdida:.0%}) ===")
    srv = Servidor(PUERTO + 2, perdida=perdida, dedup=True, con_seq=True)
    levantar(srv)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    total_intentos = 0
    for seq, m in enumerate(MENSAJES):
        resp, intentos = cliente_con_seq(sock, seq, m, (HOST, PUERTO + 2),
                                         perdida=perdida)
        total_intentos += intentos
        print(f"  seq={seq} {m.decode():8} -> "
              f"{resp.decode() if resp else 'SIN RESPUESTA':12} "
              f"({intentos} intento/s)")
    sock.close()
    time.sleep(0.3)
    srv.parar.set()
    print(f"  datagramas que recibio el servidor: {srv.recibidos}")
    print(f"  veces que hizo el TRABAJO REAL:     {srv.trabajos} "
          f"(mensajes distintos: {len(MENSAJES)})")
    if srv.trabajos == len(MENSAJES):
        print("  -> OK: la deduplicacion evito el trabajo repetido\n")
    else:
        print("  -> ERROR: deberia coincidir\n")


if __name__ == '__main__':
    args = sys.argv[1:]
    perdida = (float(args[args.index('--perdida') + 1])
               if '--perdida' in args else 0.3)
    partes = [a for a in args if a in ('--b', '--c', '--d')] or ['--b', '--c', '--d']
    for p in partes:
        {'--b': parte_b, '--c': parte_c, '--d': parte_d}[p](perdida)
