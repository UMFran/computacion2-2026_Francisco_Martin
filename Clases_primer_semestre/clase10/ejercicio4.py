import threading
import time

class ContadorHilo(threading.Thread):

    def __init__(self, nombre, limite):
        super().__init__(name=nombre)
        self.limite = limite
        self.resultado = ""

    def run(self):
        numeros = []
        for i in range(1, self.limite + 1):
            print(f"  [{self.name}] contando: {i}")
            numeros.append(str(i))
            time.sleep(0.1)
        self.resultado = ", ".join(numeros)


# Crear 3 hilos con diferentes límites
hilos = [
    ContadorHilo("Hilo-A", 3),
    ContadorHilo("Hilo-B", 5),
    ContadorHilo("Hilo-C", 4),
]

print("Iniciando hilos...\n")
for h in hilos:
    h.start()

for h in hilos:
    h.join()

print("\nResultados finales:")
print("-" * 35)
for h in hilos:
    print(f"  {h.name} (límite {h.limite}): {h.resultado}")