from multiprocessing import Pool
import time

def procesar(x):
    time.sleep(0.5)  # Simular trabajo
    return x ** 2

if __name__ == "__main__":
    # Crear pool con 4 procesos
    with Pool(4) as pool:
        # Lanzar 3 tareas asíncronas que corren en paralelo
        futuro_a = pool.apply_async(procesar, (10,))
        futuro_b = pool.apply_async(procesar, (20,))
        futuro_c = pool.apply_async(procesar, (30,))

        # Hacer otras cosas mientras tanto...
        print("Esperando...")

        # Cuando necesito los valores
        print(f"a = {futuro_a.get()}")
        print(f"b = {futuro_b.get()}")
        print(f"c = {futuro_c.get()}")

"""
futuro = pool.apply_async(procesar, (10,))

futuro.ready()                    # True si terminó (no bloquea)
futuro.successful()               # True si terminó sin excepción
futuro.wait(timeout=2)            # espera hasta 2 segundos
futuro.get(timeout=5)             # devuelve resultado o lanza TimeoutError
"""