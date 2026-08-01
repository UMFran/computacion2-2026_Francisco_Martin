import threading
import time
 
def loop_infinito(label):
    while True:
        print(f"  [{label}] trabajando...")
        time.sleep(1)
 
h = threading.Thread(target=loop_infinito, args=("no-daemon",))
h.start()
 
print("Programa principal terminó.")
print("El proceso NO cierra porque el hilo sigue vivo.")
print("Terminalo con Ctrl+C.\n")

"""
h = threading.Thread(target=loop_infinito, daemon=True)
h.start()
time.sleep(3)

print("Main terminó: el daemon muere automáticamente")
"""