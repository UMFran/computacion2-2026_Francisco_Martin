#!/usr/bin/env python3
"""Ejercicio 3, parte C: el cosechador sin bucle deja zombies.

60 hijos que mueren exactamente a la vez, para que varias SIGCHLD colapsen
en una sola.

    python3 ejercicio3_zombies.py              # handler SIN bucle (punto 8)
    python3 ejercicio3_zombies.py --con-bucle  # handler CON bucle (punto 9)

Solo Unix. Correr desde WSL, varias veces seguidas.
"""
import os
import signal
import subprocess
import sys
import time

CON_BUCLE = '--con-bucle' in sys.argv[1:]
recogidos = [0]


def cosechar(signum, frame):
    if CON_BUCLE:
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
                recogidos[0] += 1
            except ChildProcessError:
                break
    else:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)   # SIN bucle
            if pid > 0:
                recogidos[0] += 1
        except ChildProcessError:
            pass


signal.signal(signal.SIGCHLD, cosechar)

N = 60
for _ in range(N):
    if os.fork() == 0:
        time.sleep(0.5)     # todos duermen lo mismo: mueren juntos
        os._exit(0)

time.sleep(2.0)
salida = subprocess.run(['ps', '--ppid', str(os.getpid()), '-o', 'stat='],
                        capture_output=True, text=True).stdout
zombies = sum(1 for l in salida.splitlines() if l.strip().startswith('Z'))
print(f'bucle={"si" if CON_BUCLE else "no"}  hijos={N}  '
      f'recogidos={recogidos[0]}  zombies={zombies}')
