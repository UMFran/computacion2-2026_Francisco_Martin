#!/usr/bin/env python3
"""Ejercicio 1: Detectando race conditions.

1.1 CuentaInsegura: el saldo final no cuadra con las operaciones hechas.
1.2 CuentaSegura: el mismo test, con Lock, siempre cuadra.
"""
import threading
import time
import random

CANTIDAD = 10
OPERACIONES = 100
HILOS = 10


class CuentaInsegura:
    def __init__(self, saldo):
        self.saldo = saldo

    def depositar(self, cantidad):
        actual = self.saldo
        time.sleep(0.001)  # Simula procesamiento
        self.saldo = actual + cantidad

    def retirar(self, cantidad):
        actual = self.saldo
        time.sleep(0.001)
        if actual >= cantidad:
            self.saldo = actual - cantidad
            return True
        return False


class CuentaSegura:
    def __init__(self, saldo):
        self.saldo = saldo
        self.lock = threading.Lock()

    def depositar(self, cantidad):
        with self.lock:
            actual = self.saldo
            time.sleep(0.001)
            self.saldo = actual + cantidad

    def retirar(self, cantidad):
        with self.lock:
            actual = self.saldo
            time.sleep(0.001)
            if actual >= cantidad:
                self.saldo = actual - cantidad
                return True
            return False


def probar(cuenta, nombre, saldo_inicial=1000):
    """Corre el test y compara el saldo contra las operaciones realmente hechas.

    Con depositos y retiros al azar el saldo final no es un numero fijo, asi
    que para verificar hay que llevar la cuenta de lo que efectivamente paso.
    """
    hechas = []                     # (depositos, retiros_exitosos) por hilo

    def operaciones_aleatorias():
        depositos = retiros = 0
        for _ in range(OPERACIONES):
            if random.choice([True, False]):
                cuenta.depositar(CANTIDAD)
                depositos += 1
            else:
                if cuenta.retirar(CANTIDAD):
                    retiros += 1
        hechas.append((depositos, retiros))

    threads = [threading.Thread(target=operaciones_aleatorias)
               for _ in range(HILOS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    depositos = sum(d for d, _ in hechas)
    retiros = sum(r for _, r in hechas)
    esperado = saldo_inicial + CANTIDAD * (depositos - retiros)

    print(f"--- {nombre} ---")
    print(f"  {depositos} depositos y {retiros} retiros exitosos")
    print(f"  Saldo esperado: {esperado}")
    print(f"  Saldo obtenido: {cuenta.saldo}")
    if cuenta.saldo == esperado:
        print("  OK: cuadra")
    else:
        print(f"  ERROR: se perdieron {abs(esperado - cuenta.saldo)} "
              f"por actualizaciones pisadas")
    print()


if __name__ == "__main__":
    probar(CuentaInsegura(1000), "CuentaInsegura")
    probar(CuentaSegura(1000), "CuentaSegura")
