import argparse
import secrets #mejor que random para generar contraseñas seguras
import string

def crear_parser():
    parser = argparse.ArgumentParser(description="Generador de contraseñas seguras.")
 
    parser.add_argument("-n", "--length", type=int, default=12,
                        help="Longitud de la contraseña (default: 12)")
    parser.add_argument("--no-symbols", action="store_true",
                        help="Excluir símbolos especiales (!@#$%%&)")
    parser.add_argument("--no-numbers", action="store_true",
                        help="Excluir números")
    parser.add_argument("--count", type=int, default=1,
                        help="Cuántas contraseñas generar (default: 1)")
 
    return parser

def generar_password(longitud, sin_simbolos, sin_numeros):
    caracteres = string.ascii_letters
    if not sin_numeros:
        caracteres += string.digits
    if not sin_simbolos:
        caracteres += "!@#$%&"
 
    return ''.join(secrets.choice(caracteres) for _ in range(longitud))

def main():
    parser = crear_parser()
    args = parser.parse_args()
 
    for _ in range(args.count):
        password = generar_password(args.length, args.no_symbols, args.no_numbers)
        print(password)

if __name__ == "__main__":
    main()