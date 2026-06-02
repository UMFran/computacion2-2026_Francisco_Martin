import time
import multiprocessing as mp
from multiprocessing import Process

def noop():
    pass # proceso que no hace nada — mide solo creación

def medir(metodo, n=100):
    mp.set_start_method(metodo, force=True)

    inicio = time.perf_counter()
    procesos = [Process(target=noop) for _ in range(n)]
    for p in procesos:
        p.start()
    for p in procesos:
        p.join()
    total = time.perf_counter() - inicio

    print(f"[{metodo:>5}]  {n} procesos en {total:.3f}s  "
          f"({total/n*1000:.1f} ms/proceso)")
    return total

if __name__ == "__main__":
    t_fork  = medir("fork")
    t_spawn = medir("spawn")
    ratio   = t_spawn / t_fork
    print(f"\nspawn fue {ratio:.1f}x más lento que fork")