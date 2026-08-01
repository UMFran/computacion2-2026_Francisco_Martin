#!/usr/bin/env python3
"""Versión con subprocess para comparar."""
import subprocess
import sys
import time

def main():
    if len(sys.argv) < 2:
        print(f"Uso: {sys.argv[0]} comando1 [comando2 ...]")
        sys.exit(1)

    comandos = sys.argv[1:]
    inicio = time.time()

    # Iniciar todos los procesos
    procesos = []
    for cmd in comandos:
        proc = subprocess.Popen(cmd, shell=True)
        print(f"[{proc.pid}] Iniciado: {cmd}")
        procesos.append((proc, cmd))

    # Esperar a todos
    resultados = []
    for proc, cmd in procesos:
        codigo = proc.wait()
        print(f"[{proc.pid}] Terminado: {cmd} (código: {codigo})")
        resultados.append(codigo)

    duracion = time.time() - inicio

    exitosos = sum(1 for c in resultados if c == 0)
    print(f"\nResumen:")
    print(f"- Comandos ejecutados: {len(comandos)}")
    print(f"- Exitosos: {exitosos}")
    print(f"- Fallidos: {len(comandos) - exitosos}")
    print(f"- Tiempo total: {duracion:.2f}s")

if __name__ == "__main__":
    main()