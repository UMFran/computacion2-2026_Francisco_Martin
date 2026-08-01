import argparse
import json
import sys

def crear_parser():
    parser = argparse.ArgumentParser(description="Procesador de archivos JSON.")
 
    parser.add_argument("archivo", help="Archivo JSON (o '-' para stdin)")

    parser.add_argument("--keys",   action="store_true", help="Listar claves del primer nivel")
    parser.add_argument("--get",    metavar="KEY",       help="Obtener valor (ej: usuario.nombre)")
    parser.add_argument("--pretty", action="store_true", help="Formatear con indentación")
    parser.add_argument("--set",    nargs=2, metavar=("KEY", "VALUE"), help="Modificar un valor")
    parser.add_argument("-o", "--output", default="-",  help="Archivo de salida (default: stdout)")
 
    return parser

def leer_json(archivo):
    """Lee JSON desde un archivo o desde stdin si el archivo es '-'."""
    if archivo == "-":
        return json.load(sys.stdin)
    with open(archivo, "r") as f:
        return json.load(f)

def navegar(datos, ruta):
    """
    Navega el JSON usando notación con puntos.
    "usuario.nombre"  →  datos["usuario"]["nombre"]
    "productos.0.precio"  →  datos["productos"][0]["precio"]
    """
    partes = ruta.split(".")
    actual = datos
    for parte in partes:
        if isinstance(actual, list):
            # Si es una lista, la parte tiene que ser un número (índice)
            actual = actual[int(parte)]
        else:
            actual = actual[parte]
    return actual
 
def modificar(datos, ruta, valor):
    """
    Navega hasta el penúltimo nivel y modifica el último valor.
    Convierte el valor string al tipo correcto (true → bool, números → int/float).
    """
    partes = ruta.split(".")
    actual = datos
 
    # Llegar al penúltimo nivel
    for parte in partes[:-1]:
        if isinstance(actual, list):
            actual = actual[int(parte)]
        else:
            actual = actual[parte]
 
    # Convertir el valor al tipo correcto
    ultima_clave = partes[-1]
    if valor == "true":
        valor_convertido = True
    elif valor == "false":
        valor_convertido = False
    else:
        try:
            valor_convertido = int(valor)
        except ValueError:
            try:
                valor_convertido = float(valor)
            except ValueError:
                valor_convertido = valor  # queda como string
 
    # Asignar el valor
    if isinstance(actual, list):
        actual[int(ultima_clave)] = valor_convertido
    else:
        actual[ultima_clave] = valor_convertido
 
    return datos
 
def escribir(datos, destino, pretty=False):
    """Escribe JSON en un archivo o en stdout si destino es '-'."""
    indent = 4 if pretty else None
    contenido = json.dumps(datos, indent=indent, ensure_ascii=False)
 
    if destino == "-":
        print(contenido)
    else:
        with open(destino, "w") as f:
            f.write(contenido + "\n")
        print(f"Guardado en {destino}")
 
def main():
    parser = crear_parser()
    args = parser.parse_args()
 
    try:
        datos = leer_json(args.archivo)
    except FileNotFoundError:
        print(f"Error: No se encuentra '{args.archivo}'", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: JSON inválido — {e}", file=sys.stderr)
        sys.exit(1)
 
    if args.keys:
        for clave in datos.keys():
            print(clave)
 
    elif args.get:
        try:
            valor = navegar(datos, args.get)
            print(json.dumps(valor, ensure_ascii=False))
        except (KeyError, IndexError, TypeError):
            print(f"Error: no existe la ruta '{args.get}'", file=sys.stderr)
            sys.exit(1)
 
    elif args.pretty:
        escribir(datos, args.output, pretty=True)
 
    elif args.set:
        clave, valor = args.set
        try:
            datos = modificar(datos, clave, valor)
            escribir(datos, args.output, pretty=True)
        except (KeyError, IndexError, TypeError):
            print(f"Error: no existe la ruta '{clave}'", file=sys.stderr)
            sys.exit(1)
 
    else:
        escribir(datos, args.output)
 
if __name__ == "__main__":
    main()