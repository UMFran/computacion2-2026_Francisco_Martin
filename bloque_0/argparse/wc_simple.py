import sys

#CASO 1: No se especifica un archivo
if len(sys.argv) < 2:
    print("Error: Debe especificar un archivo")
    sys.exit(1)

archivo = sys.argv[1]

#CASO 2: El archivo no existe o no se puede leer
try:
    with open(archivo, 'r') as f:
        lineas = f.readlines()

except FileNotFoundError:
    print(f"Error: No se puede leer '{archivo}'")
    sys.exit(1)

#CASO 3: Archivo leído correctamente
print(f"Lineas: {len(lineas)}")