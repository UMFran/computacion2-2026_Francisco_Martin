import mmap

BUSCAR     = b"Python"   # 6 bytes
REEMPLAZAR = b"mmap  "   # 6 bytes (mismo largo — requisito del reemplazo in-place)

with open("demo.txt", "r+b") as f:
    with mmap.mmap(f.fileno(), 0) as mm:
        pos = mm.find(BUSCAR)          # Busca la posición exacta en bytes
        mm[pos : pos + len(BUSCAR)] = REEMPLAZAR  # Reemplaza in-place
        mm.flush()                     # Vuelca los cambios al disco