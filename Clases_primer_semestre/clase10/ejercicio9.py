import threading
import queue
import urllib.request
import urllib.error
import time

def worker(in_q, out_list, lock):
    while True:
        url = in_q.get()
        if url is None:
            in_q.task_done()
            break
        inicio = time.time()
        try:
            response = urllib.request.urlopen(url, timeout=10)
            datos = response.read()
            with lock:
                out_list.append({
                    "url": url,
                    "ok": True,
                    "bytes": len(datos),
                    "tiempo": time.time() - inicio,
                })
        except Exception as e:
            with lock:
                out_list.append({
                    "url": url,
                    "ok": False,
                    "error": str(e),
                    "tiempo": time.time() - inicio,
                })
        in_q.task_done()

if __name__ == "__main__":
    urls = [
        "https://www.python.org",
        "https://docs.python.org",
        "https://pypi.org",
        "https://www.google.com",
        "https://www.github.com",
    ]
    NUM_WORKERS = 4

    in_q = queue.Queue()
    resultados = []
    lock = threading.Lock()

    workers = [
        threading.Thread(target=worker, args=(in_q, resultados, lock))
        for _ in range(NUM_WORKERS)
    ]
    for w in workers: w.start()

    inicio = time.time()
    for url in urls:
        in_q.put(url)

    # Señales de fin
    for _ in workers:
        in_q.put(None)

    for w in workers:
        w.join()

    tiempo_total = time.time() - inicio

    ok = sum(1 for r in resultados if r["ok"])
    bytes_total = sum(r.get("bytes", 0) for r in resultados)
    print(f"\nDescargas exitosas: {ok}/{len(urls)}")
    print(f"Bytes totales: {bytes_total:,}")
    print(f"Tiempo total: {tiempo_total:.2f}s")