import cowsay
import sys

mensaje = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else "Hola Docker 2!"
cowsay.cow(mensaje)