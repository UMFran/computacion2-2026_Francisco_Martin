#!/usr/bin/env python3
"""Pipeline de 3 etapas con multiprocessing."""
from multiprocessing import Process, Queue
import time

def etapa_multiplicar(input_q, output_q):
    while True:
        item = input_q.get()
        if item is None:
            output_q.put(None)
            break
        time.sleep(0.05)
        output_q.put(item * 2)

def etapa_sumar(input_q, output_q):
    while True:
        item = input_q.get()
        if item is None:
            output_q.put(None)
            break
        time.sleep(0.05)
        output_q.put(item + 10)

def etapa_formatear(input_q, output_q):
    while True:
        item = input_q.get()
        if item is None:
            output_q.put(None)
            break
        time.sleep(0.05)
        output_q.put(f"resultado_{item:03d}")

if __name__ == "__main__":
    q1, q2, q3, q4 = Queue(), Queue(), Queue(), Queue()

    p1 = Process(target=etapa_multiplicar, args=(q1, q2))
    p2 = Process(target=etapa_sumar, args=(q2, q3))
    p3 = Process(target=etapa_formatear, args=(q3, q4))

    p1.start(); p2.start(); p3.start()

    # Alimentar el pipeline
    for i in range(10):
        q1.put(i)
    q1.put(None)

    # Recoger resultados
    while True:
        result = q4.get()
        if result is None:
            break
        print(f"Final: {result}")

    p1.join(); p2.join(); p3.join()

"""
Preguntas:

¿Qué pasa si una etapa es mucho más lenta que las otras?
¿Cómo escalarías la etapa lenta?

Respuestas
Si una etapa es mucho más lenta que las otras:
el pipeline se queda limitado por esa etapa lenta
las colas acumulan datos entre etapas hasta cierto punto
las etapas más rápidas terminarán esperando, porque la etapa lenta se convierte en cuello de botella

Cómo escalar la etapa lenta:
añadir más procesos para esa etapa lenta
usar múltiples workers que lean de la misma cola de entrada y escriban en la misma cola de salida
así se paraleliza la etapa lenta y se mejora el throughput
"""