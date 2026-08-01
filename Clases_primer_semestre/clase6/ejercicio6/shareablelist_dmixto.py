#!/usr/bin/env python3
"""ShareableList para compartir datos de distintos tipos."""
from multiprocessing import Process, shared_memory

def actualizar_datos(nombre_shm):
    """Actualiza datos en la lista compartida."""
    sl = shared_memory.ShareableList(name=nombre_shm)

    # Modificar valores
    sl[0] = 42              # int
    sl[1] = 3.14159         # float
    sl[2] = "actualizado"   # str (máx largo del original)
    sl[3] = False           # bool

    print(f"[WORKER] Lista actualizada: {list(sl)}")
    sl.shm.close()

# Crear lista compartida con valores iniciales
# OJO: el tipo y tamaño máximo de cada elemento se fija en la creación
sl = shared_memory.ShareableList(
    [0, 0.0, "          ", True],  # Espacios para reservar lugar para strings
    name="mi_lista_comp"
)

print(f"Antes:   {list(sl)}")

p = Process(target=actualizar_datos, args=(sl.shm.name,))
p.start()
p.join()

print(f"Después: {list(sl)}")

sl.shm.close()
sl.shm.unlink()