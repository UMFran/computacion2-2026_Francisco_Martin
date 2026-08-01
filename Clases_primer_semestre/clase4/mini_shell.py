#!/usr/bin/env python3
"""Mini-shell con redirección."""
import os
import sys

def parsear_linea(linea):
    """
    Parsea una línea de comando.
    Retorna (comando, args, archivo_salida, archivo_entrada)

    Ejemplos:
      "ls -la" -> ("ls", ["-la"], None, None)
      "ls > out.txt" -> ("ls", [], "out.txt", None)
      "cat < in.txt" -> ("cat", [], None, "in.txt")
    """
    # TODO: implementar
    partes = linea.split()
    comando = partes[0] if partes else None
    args = []
    archivo_salida = None
    archivo_entrada = None

    # Buscar > y <
    i = 1
    while i < len(partes):
        if partes[i] == ">":
            archivo_salida = partes[i + 1]
            i += 2
        elif partes[i] == "<":
            archivo_entrada = partes[i + 1]
            i += 2
        else:
            args.append(partes[i])
            i += 1

    return comando, args, archivo_salida, archivo_entrada

def ejecutar(comando, args, archivo_salida=None, archivo_entrada=None):
    """Ejecuta un comando con redirección opcional."""
    pid = os.fork()

    if pid == 0:
        # Configurar redirecciones ANTES del exec

        if archivo_salida:
            fd = os.open(archivo_salida, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
            os.dup2(fd, 1)  # stdout -> archivo
            os.close(fd)

        if archivo_entrada:
            fd = os.open(archivo_entrada, os.O_RDONLY)
            os.dup2(fd, 0)  # stdin <- archivo
            os.close(fd)

        # Ejecutar
        try:
            os.execvp(comando, [comando] + args)
        except OSError as e:
            print(f"Error: {e}", file=sys.stderr)
            os._exit(127)

    else:
        _, status = os.wait()
        return os.WEXITSTATUS(status)

def main():
    while True:
        try:
            linea = input("minish$ ")
        except EOFError:
            print("\nChau!")
            break

        linea = linea.strip()
        if not linea:
            continue

        if linea == "exit":
            break

        comando, args, salida, entrada = parsear_linea(linea)
        if comando:
            ejecutar(comando, args, salida, entrada)

if __name__ == "__main__":
    main()