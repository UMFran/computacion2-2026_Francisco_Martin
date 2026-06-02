from multiprocessing import Pool
import time

def procesar(x):
    time.sleep(0.5)  # Simular trabajo
    return x ** 2

if __name__ == "__main__":
    # Crear pool con 4 procesos
    with Pool(4) as pool:
        for r in pool.imap(procesar, range(10)):
            print(f"Recibido: {r}")  # imprime apenas el primero está listo

"""
with Pool(4) as pool:
    for r in pool.imap_unordered(procesar, range(10)):
        print(f"Terminó: {r}")  # llega el primero que terminó, sin importar su índice
"""