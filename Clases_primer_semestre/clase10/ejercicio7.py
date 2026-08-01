import threading
import queue
import time

resultados = {}
resultados_lock = threading.Lock()

def procesar_imagen(nombre):
    time.sleep(0.5)
    return f"{nombre} -> procesada"

def worker(q, worker_id):
    contador = 0
    while True:
        imagen = q.get()
        if imagen is None:
            break
        resultado = procesar_imagen(imagen)
        print(f"Worker-{worker_id}: {resultado}")
        contador += 1
        q.task_done()

    with resultados_lock:
        resultados[f"Worker-{worker_id}"] = contador

cola = queue.Queue()

workers = [
    threading.Thread(target=worker, args=(cola, i))
    for i in range(4)
]
for w in workers: w.start()

inicio = time.perf_counter()
for i in range(1, 21):
    cola.put(f"imagen_{i:03d}.jpg")

cola.join()

for _ in workers:
    cola.put(None)
for w in workers:
    w.join()

tiempo = time.perf_counter() - inicio
print(f"\nTiempo total: {tiempo:.2f}s")
print("\nImagenes por worker:")
for nombre, cant in resultados.items():
    print(f"  {nombre}: {cant} imágenes")