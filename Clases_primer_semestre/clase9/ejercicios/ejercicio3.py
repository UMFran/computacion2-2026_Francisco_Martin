#!/usr/bin/env python3
"""Memoria compartida con Value y Array."""
from multiprocessing import Process, Value, Array
import time

def incrementar(contador, n_veces, id):
    for _ in range(n_veces):
        # get_lock() previene race conditions (estudiado formalmente en clase 10)
        with contador.get_lock():
            contador.value += 1
    print(f"Worker {id} terminó sus {n_veces} incrementos")

def llenar_array(arr, valor_inicial, id):
    """Cada worker llena su segmento del array."""
    inicio = id * (len(arr) // 4)
    fin = inicio + (len(arr) // 4)
    for i in range(inicio, fin):
        arr[i] = valor_inicial + i

if __name__ == "__main__":
    # Value compartido con auto-lock
    contador = Value('i', 0)

    procs = [Process(target=incrementar, args=(contador, 10000, i))
             for i in range(4)]

    for p in procs:
        p.start()
    for p in procs:
        p.join()

    print(f"\nContador final: {contador.value}")
    assert contador.value == 40000, "¡Race condition! Falta el lock"

    # Array compartido, particionado por worker
    arr = Array('i', 100)
    procs = [Process(target=llenar_array, args=(arr, 1000, i))
             for i in range(4)]

    for p in procs:
        p.start()
    for p in procs:
        p.join()

    print(f"Array completo (primeros 10): {list(arr)[:10]}")
    print(f"Array completo (últimos 10): {list(arr)[-10:]}")

"""
Respuestas
¿Qué pasa si quitás with contador.get_lock():?

entonces los incrementos no se sincronizan
dos procesos pueden leer el mismo valor y escribir el mismo resultado
eso causa race conditions y el contador final puede quedar menor que el esperado
¿Necesitarías un lock para el Array en este caso?

no, porque cada worker escribe en un segmento diferente del array
no hay solapamiento de índices entre procesos, así que no hay conflicto
si los procesos escribieran en posiciones compartidas, sí sería necesario un lock
"""