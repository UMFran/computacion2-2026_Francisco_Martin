#!/usr/bin/env python3
"""Ejercicio 1: generadores que reciben."""


# ---- 1.1 send() ----

def acumulador():
    total = 0
    while True:
        n = yield total
        total += n


def parte_1_1():
    print("=== 1.1 send() ===")

    # Punto 1: send() antes del next() inicial
    a = acumulador()
    try:
        a.send(10)
    except TypeError as e:
        print(f"  send(10) sin next() -> TypeError: {e}")

    # Punto 2: el next() inicial
    a = acumulador()
    print(f"  next(a) inicial devuelve: {next(a)}")

    # Punto 3: tres send() seguidos
    for n in (10, 5, 100):
        print(f"  a.send({n}) -> {a.send(n)}")
    print()


# ---- 1.2 El estado sobrevive ----

def contador():
    n = 0
    while True:
        print(f'  voy por {n}')
        yield
        n += 1


def parte_1_2():
    print("=== 1.2 el estado sobrevive ===")
    c1 = contador()
    c2 = contador()
    print("  alternando entre dos generadores:")
    next(c1); next(c2); next(c1); next(c2); next(c1)
    print()


# ---- 1.3 StopIteration lleva el resultado ----

def tarea():
    yield 'trabajando'
    return 'resultado final'


def parte_1_3():
    print("=== 1.3 StopIteration lleva el resultado ===")
    t = tarea()
    print(f"  next(t) -> {next(t)!r}")
    try:
        next(t)
    except StopIteration as e:
        print(f"  StopIteration.value -> {e.value!r}")
    print()


if __name__ == "__main__":
    parte_1_1()
    parte_1_2()
    parte_1_3()
