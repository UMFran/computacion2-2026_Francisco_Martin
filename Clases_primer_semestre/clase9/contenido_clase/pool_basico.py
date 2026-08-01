from multiprocessing import Pool
import time

def procesar(x):
    time.sleep(0.5)  # Simular trabajo
    return x ** 2

if __name__ == "__main__":
    # Crear pool con 4 procesos
    with Pool(4) as pool:
        # map: aplica función a cada elemento (bloquea hasta terminar todo)
        resultados = pool.map(procesar, range(10))
        print(f"map: {resultados}")