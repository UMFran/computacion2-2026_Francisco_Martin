#!/usr/bin/env python3
"""Ejercicio 2 (OBLIGATORIO): construir el scheduler.

    python3 ejercicio2.py --a    # Parte A: el intercalado
    python3 ejercicio2.py --b    # Parte B: la tarea egoista
    python3 ejercicio2.py --c    # Parte C: agregar tiempo
    python3 ejercicio2.py --d    # Parte D: yield from
    python3 ejercicio2.py        # todas
"""
import sys
import time
from collections import deque

reanudaciones = 0       # punto 2: contador de llamadas a next()


# ---------------------------------------------------------------
# Parte A: el intercalado
# ---------------------------------------------------------------

def tarea(nombre, pasos):
    """Imprime cada paso y cede el control."""
    for i in range(1, pasos + 1):
        print(f'  [{nombre}] paso {i}/{pasos}')
        yield


def scheduler(tareas):
    """Event loop cooperativo: reanuda una tarea por vuelta."""
    global reanudaciones
    pendientes = deque(tareas)
    while pendientes:
        t = pendientes.popleft()
        try:
            reanudaciones += 1
            next(t)                 # reanudar hasta el proximo yield
        except StopIteration:
            continue                # termino: no vuelve a la cola
        pendientes.append(t)        # cedio: va al final de la cola


def parte_a():
    global reanudaciones
    reanudaciones = 0
    print("=== Parte A: el intercalado ===")
    scheduler([tarea('A', 3), tarea('B', 2), tarea('C', 4)])
    print(f"  reanudaciones (llamadas a next): {reanudaciones}")

    # Punto 3: una tarea sin ningun yield
    def sin_yield(nombre):
        print(f'  [{nombre}] no cedo nunca')
        return
        yield                       # inalcanzable, pero la hace generador

    reanudaciones = 0
    print("  --- tarea sin yield ejecutable ---")
    scheduler([sin_yield('X'), tarea('Y', 2)])
    print(f"  reanudaciones: {reanudaciones}\n")


# ---------------------------------------------------------------
# Parte B: la cooperacion es obligatoria
# ---------------------------------------------------------------

def tarea_egoista(nombre):
    print(f'  [{nombre}] me pongo a calcular')
    time.sleep(3)              # no cede el control
    print(f'  [{nombre}] listo')
    yield


def parte_b():
    print("=== Parte B: la tarea egoista ===")
    inicio = time.perf_counter()
    scheduler([tarea('A', 3), tarea_egoista('EGOISTA'), tarea('B', 3)])
    print(f"  total: {time.perf_counter() - inicio:.1f}s "
          f"(3s son de la tarea egoista)\n")


# ---------------------------------------------------------------
# Parte C: agregar tiempo
# ---------------------------------------------------------------

def dormir(segundos):
    """Cede informando CUANDO quiere volver.

    No puede llamar a time.sleep(): eso bloquearia el hilo entero y las
    demas tareas no avanzarian (es justo el problema de la parte B).
    """
    yield time.perf_counter() + segundos


def tarea_lenta(nombre, espera, veces=2):
    for i in range(1, veces + 1):
        print(f'  [{nombre}] duermo {espera}s ({i}/{veces})')
        yield from dormir(espera)       # delega: el valor sube al scheduler
        print(f'  [{nombre}] desperte')


def scheduler_tiempo(tareas):
    """Scheduler que entiende esperas."""
    global reanudaciones
    pendientes = deque((t, 0.0) for t in tareas)    # (tarea, cuando_volver)
    while pendientes:
        t, cuando = pendientes.popleft()
        ahora = time.perf_counter()
        if ahora < cuando:
            # Todavia no le toca: al final de la cola.
            pendientes.append((t, cuando))
            if all(ahora < c for _, c in pendientes):
                # Nadie esta listo: dormir hasta el mas proximo en vez de
                # girar en un busy loop.
                time.sleep(min(c for _, c in pendientes) - ahora)
            continue
        try:
            reanudaciones += 1
            proximo = next(t)
        except StopIteration:
            continue
        pendientes.append((t, proximo if proximo else 0.0))


def parte_c():
    global reanudaciones
    reanudaciones = 0
    print("=== Parte C: agregar tiempo ===")
    inicio = time.perf_counter()
    scheduler_tiempo([tarea_lenta('A', 0.15), tarea_lenta('B', 0.15),
                      tarea_lenta('C', 0.15)])
    total = time.perf_counter() - inicio
    print(f"  total: {total:.3f}s")
    print(f"  suma de las esperas: 3 tareas x 2 veces x 0.15s = 0.90s")
    print(f"  -> las esperas se SOLAPAN: {total:.3f}s < 0.90s\n")


# ---------------------------------------------------------------
# Parte D: yield from
# ---------------------------------------------------------------

def tarea_sin_yield_from(nombre, espera):
    print(f'  [{nombre}] llamo a dormir() SIN yield from')
    dormir(espera)              # crea el generador y lo tira a la basura
    print(f'  [{nombre}] "desperte" (no espero nada)')
    yield


def parte_d():
    print("=== Parte D: yield from ===")
    print("  con yield from:")
    inicio = time.perf_counter()
    scheduler_tiempo([tarea_lenta('CON', 0.3, veces=1)])
    print(f"    tardo {time.perf_counter() - inicio:.3f}s")

    print("  sin yield from:")
    inicio = time.perf_counter()
    scheduler_tiempo([tarea_sin_yield_from('SIN', 0.3)])
    print(f"    tardo {time.perf_counter() - inicio:.3f}s "
          f"(no espero: el generador nunca se ejecuto)\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    partes = [a for a in args if a in ('--a', '--b', '--c', '--d')]
    if not partes:
        partes = ['--a', '--b', '--c', '--d']
    for p in partes:
        {'--a': parte_a, '--b': parte_b, '--c': parte_c, '--d': parte_d}[p]()
