import time
import random
from multiprocessing import Process

def worker(worker_id):
    espera = random.uniform(0.5, 2.0)
    print(f"  Worker {worker_id} arrancó — va a dormir {espera:.2f}s")
    time.sleep(espera)
    print(f"  Worker {worker_id} terminó")

if __name__ == "__main__":
    procesos = []
    inicio = time.time()

    for i in range(5):
        p = Process(target=worker, args=(i,))
        procesos.append(p)
        p.start()

    for p in procesos:
        p.join()                        # espera a cada uno

    total = time.time() - inicio
    print(f"\nTodos los workers terminaron en {total:.2f}s")