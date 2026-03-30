import argparse
from html import parser

def crear_parser():
    parser = argparse.ArgumentParser(description="Convierte temperaturas entre Celsius y Fahrenheit.")
    parser.add_argument("valor", type=float, help="Temperatura a convertir")
    parser.add_argument("-t", "--to", choices=["celsius", "fahrenheit"], required=True, help="Unidad de destino")
    return parser

def convertir(valor, destino):
    if destino == "celsius":
        resultado = (valor - 32) * 5.0/9.0
        return f"{valor:.0f}°F = {resultado:.2f}°C"
    elif destino == "fahrenheit":
        resultado = valor * 9.0/5.0 + 32
        return f"{valor:.0f}°C = {resultado:.1f}°F"

def main():
    parser = crear_parser()
    args = parser.parse_args()
    print(convertir(args.valor, args.to))

if __name__ == "__main__":
    main()