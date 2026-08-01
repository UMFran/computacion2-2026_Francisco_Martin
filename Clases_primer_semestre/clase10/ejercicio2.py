import threading
import time

URLS = [f"http://servidor.com/archivo_{i}.zip" for i in range(5)]
DEMORA = 1  # segundos por descarga

def simular_descarga(url, demora):
    print(f"  Iniciando descarga: {url}")
    time.sleep(demora)
    print(f"  ✓ Completada:       {url}")

# ── 1. Secuencial ────────────────────────────────────────────────────────────
print("=" * 55)
print("SECUENCIAL")
print("=" * 55)
inicio = time.time()
 
for url in URLS:
    simular_descarga(url, DEMORA)
 
tiempo_secuencial = time.time() - inicio
print(f"\nTiempo secuencial: {tiempo_secuencial:.2f}s\n")
 
# ── 2. Threading ─────────────────────────────────────────────────────────────
print("=" * 55)
print("THREADING (paralelo)")
print("=" * 55)
inicio = time.time()
 
hilos = [
    threading.Thread(target=simular_descarga, args=(url, DEMORA))
    for url in URLS
]
 
for h in hilos:
    h.start()
 
for h in hilos:
    h.join()
 
tiempo_threading = time.time() - inicio
print(f"\nTiempo threading:  {tiempo_threading:.2f}s\n")
print(f"Mejora:     {tiempo_secuencial / tiempo_threading:.1f}x")