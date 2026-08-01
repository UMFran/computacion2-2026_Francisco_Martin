from itertools import islice


def chunked(iterable, size):
    """
    Divide cualquier iterable en chunks de tamaño 'size'.
    Es lazy: no carga todo en memoria, genera un chunk a la vez.
    """
    iterador = iter(iterable)      # convierte cualquier iterable en iterador
    while True:
        # islice toma hasta 'size' elementos del iterador sin consumir el resto
        chunk = list(islice(iterador, size))
        if not chunk:              # si el iterador se agotó, paramos
            return
        yield chunk                # devuelve el chunk y pausa hasta el próximo next()


# ── Pruebas ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("=== range(10) en grupos de 3 ===")
    print(list(chunked(range(10), 3)))

    print("\n=== string en grupos de 3 ===")
    print(list(chunked("abcdefgh", 3)))

    print("\n=== lista exacta (sin resto) ===")
    print(list(chunked(range(9), 3)))

    print("\n=== iterable vacío ===")
    print(list(chunked([], 3)))

    print("\n=== caso práctico: procesar en batches ===")
    datos = range(1, 26)   # 25 elementos
    for i, batch in enumerate(chunked(datos, 10), 1):
        print(f"  Batch {i}: {batch}")

    print("\n=== es lazy: el generador no calcula todo de entrada ===")
    gen = chunked(range(1_000_000), 100)  # un millón de elementos
    print(f"  Primer chunk: {next(gen)[:5]}... (solo calculó 100, no 1.000.000)")