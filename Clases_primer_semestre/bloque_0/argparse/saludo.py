import sys


if len(sys.argv) < 2:
    print(f"Uso: {sys.argv[0]} <nombre>")
    sys.exit(1)

nombre = " ".join(sys.argv[1:])
print(f"Hola, {nombre}")