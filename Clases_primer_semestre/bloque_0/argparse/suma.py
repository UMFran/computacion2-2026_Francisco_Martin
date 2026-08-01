import sys

if len(sys.argv) < 2:
    print("Suma: 0")
    sys.exit(0)

numeros = []
for arg in sys.argv[1:]:
    try:
        numero = float(arg)
        numeros.append(numero)
    except ValueError:
        print(f"Advertencia: '{arg}' no es un número válido y se ignorará.", file=sys.stderr)
resultado = sum(numeros)
if resultado == int(resultado) and all('.' not in arg for arg in sys.argv[1:]):
    print(f"Resultado: {int(resultado)}")
else: 
    print(f"Resultado: {resultado}")