#!/usr/bin/env python3
"""Ejercicio 6: Demostración y prevención de deadlock."""
import threading
import time


# Versión con deadlock potencial
def demostrar_deadlock():
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def thread_1():
        with lock_a:
            print("Thread 1: tiene A")
            time.sleep(0.1)
            with lock_b:
                print("Thread 1: tiene A y B")

    def thread_2():
        with lock_b:
            print("Thread 2: tiene B")
            time.sleep(0.1)
            with lock_a:
                print("Thread 2: tiene B y A")

    # daemon=True: los dos hilos quedan trabados para siempre, y si no son
    # daemon el proceso no puede terminar aunque el script llegue al final
    # (habria que cortarlo con Ctrl+C todas las veces).
    t1 = threading.Thread(target=thread_1, daemon=True)
    t2 = threading.Thread(target=thread_2, daemon=True)

    t1.start()
    t2.start()

    # Timeout para detectar deadlock
    t1.join(timeout=2)
    t2.join(timeout=2)

    if t1.is_alive() or t2.is_alive():
        print("¡DEADLOCK DETECTADO!")
        return False
    return True


# Versión corregida: orden consistente
def version_corregida():
    lock_a = threading.Lock()
    lock_b = threading.Lock()

    def thread_ordenado(nombre):
        with lock_a:  # Siempre A primero
            print(f"{nombre}: tiene A")
            with lock_b:  # Luego B
                print(f"{nombre}: tiene A y B")
                time.sleep(0.1)

    t1 = threading.Thread(target=thread_ordenado, args=("Thread 1",))
    t2 = threading.Thread(target=thread_ordenado, args=("Thread 2",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    print("¡Completado sin deadlock!")


if __name__ == "__main__":
    print("=== Versión con deadlock ===")
    demostrar_deadlock()

    print("\n=== Versión corregida ===")
    version_corregida()
