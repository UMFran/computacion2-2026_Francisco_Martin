#!/usr/bin/env python3
"""Compartir datos con SharedMemory entre procesos."""
from multiprocessing import Process, shared_memory
import struct

def productor(shm_name, num_valores):
    """Produce valores en la memoria compartida."""
    shm = shared_memory.SharedMemory(name=shm_name)

    for i in range(num_valores):
        struct.pack_into('i', shm.buf, i * 4, i * i)

    # Marcar como listo (último byte)
    shm.buf[-1] = 1

    print(f"[PRODUCTOR] Escribí {num_valores} valores")
    shm.close()

def consumidor(shm_name, num_valores):
    """Lee valores de la memoria compartida."""
    shm = shared_memory.SharedMemory(name=shm_name)

    # Esperar a que el productor termine (polling simple)
    import time
    while shm.buf[-1] != 1:
        time.sleep(0.01)

    valores = []
    for i in range(num_valores):
        val = struct.unpack_from('i', shm.buf, i * 4)[0]
        valores.append(val)

    print(f"[CONSUMIDOR] Leí: {valores}")
    shm.close()

# Crear memoria compartida
NUM = 10
shm = shared_memory.SharedMemory(create=True, size=NUM * 4 + 1)

p_prod = Process(target=productor, args=(shm.name, NUM))
p_cons = Process(target=consumidor, args=(shm.name, NUM))

p_cons.start()
p_prod.start()

p_prod.join()
p_cons.join()

shm.close()
shm.unlink()