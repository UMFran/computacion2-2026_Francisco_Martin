import argparse
from pathlib import Path 

def crear_parser():
    parser = argparse.ArgumentParser(description="Listar archivos en un directorio")
    parser.add_argument("directorio", nargs="?", default=".", help="Directorio a listar (por defecto: directorio actual)")
    parser.add_argument("-a", "--all", action="store_true", help="Incluir archivos ocultos")
    parser.add_argument("--extension", nargs="?", help="Filtrar por extensión de archivo (ejemplo: .txt)")
    return parser

def listar(directorio, mostrar_ocultos, extension):
    path = Path(directorio)

    if not path.exists():
        print(f"Error: El directorio {directorio} no existe.")
        return False
    if not path.is_dir():
        print(f"Error: {directorio} no es un directorio válido.")
        return False
    
    elementos = sorted(path.iterdir())
    for elemento in elementos:
        nombre = elemento.name

        if nombre.startswith(".") and not mostrar_ocultos:
            continue
        if extension and not nombre.endswith(extension):
            continue
        if elemento.is_dir():
            print(nombre + "/")
        else:            
            print(nombre)
    return True

def main():
    parser = crear_parser()
    args = parser.parse_args()
    listar(args.directorio, args.all, args.extension)

if __name__ == "__main__":    
    main()