import time
from contextlib import contextmanager


# ── Implementación 1: Clase con __enter__ y __exit__ ────────────────────────

class Timer:
    def __init__(self, nombre=None):
        self.nombre  = nombre
        self.elapsed = 0.0        # tiempo acumulado, accesible en cualquier momento
        self._inicio = None

    def __enter__(self):
        self._inicio = time.perf_counter()  # marca el momento de entrada al bloque
        return self                          # el "as t" recibe este objeto

    def __exit__(self, *args):
        # Este método se llama automáticamente al salir del bloque with
        self.elapsed = time.perf_counter() - self._inicio
        if self.nombre:
            print(f"[Timer] {self.nombre}: {self.elapsed:.3f}s")
        # Devolver None/False no suprime excepciones (comportamiento correcto)


# ── Implementación 2: Usando @contextmanager ────────────────────────────────

@contextmanager
def timer(nombre=None):
    """
    Versión funcional con @contextmanager.
    Todo lo que está ANTES del yield es el __enter__.
    Todo lo que está DESPUÉS del yield es el __exit__.
    El yield entrega el objeto al bloque 'with'.
    """
    class _Estado:
        elapsed = 0.0

    estado = _Estado()
    inicio = time.perf_counter()
    try:
        yield estado                        # el "as t" recibe este objeto
    finally:
        estado.elapsed = time.perf_counter() - inicio
        if nombre:
            print(f"[timer] {nombre}: {estado.elapsed:.3f}s")


# ── Pruebas ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Implementación 1: Clase ===\n")

    # Con nombre → imprime automáticamente al salir
    with Timer("Procesamiento de datos"):
        datos = [x**2 for x in range(1000000)]

    # Sin nombre → solo guarda elapsed
    with Timer() as t:
        time.sleep(0.5)
    print(f"El bloque tardó {t.elapsed:.3f} segundos")

    # Acceso a elapsed DURANTE el bloque
    with Timer() as t:
        time.sleep(0.1)
        print(f"  Después del paso 1: {t.elapsed:.3f}s")
        time.sleep(0.1)
        print(f"  Después del paso 2: {t.elapsed:.3f}s")

    print()
    print("=== Implementación 2: @contextmanager ===\n")

    with Timer("Procesamiento de datos"):
        datos = [x**2 for x in range(1000000)]

    with Timer() as t:
        time.sleep(0.5)
    print(f"El bloque tardó {t.elapsed:.3f} segundos")