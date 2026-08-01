import threading
import time
 
def contar(nombre):
    for i in range(1, 6):
        print(f"{nombre}: {i}")
        time.sleep(0.2)
 
# Crear los 3 hilos
hilos = [
    threading.Thread(target=contar, args=(f"Hilo-{n}",))
    for n in range(1, 4)
]
 
# Lanzar todos los hilos
for h in hilos:
    h.start()
 
# Esperar a que todos terminen
for h in hilos:
    h.join()
 
print("Listo")
 