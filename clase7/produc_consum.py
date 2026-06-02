import time
import random
from multiprocessing import Process, Queue

def productor(q):
    for i in range(10):
        item = f"item-{i}"
        time.sleep(random.uniform(0.1, 0.4)) # simula generación
        q.put(item)
        print(f"[PROD] puso {item}")
    q.put(None) # señal de fin

def consumidor(q):
    while True:
        item = q.get() # bloquea hasta que haya algo
        if item is None:
            print("[CONS] recibió señal de fin, cerrando")
            break
        time.sleep(random.uniform(0.2, 0.5) )# simula procesamiento
        print(f"[CONS] procesó {item}")

if __name__ == "__main__":
    q = Queue()

    prod = Process(target=productor, args=(q,))
    cons = Process(target=consumidor, args=(q,))

    cons.start()
    prod.start()

    prod.join()
    cons.join()

    print("Listo.")