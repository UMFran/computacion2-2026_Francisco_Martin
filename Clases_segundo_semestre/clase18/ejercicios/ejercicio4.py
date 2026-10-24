#!/usr/bin/env python3
"""Ejercicio 4: asyncio de verdad.

El scheduler de la parte A, ahora con asyncio.
"""
import asyncio
import time


# ---- 4.1 El equivalente ----

async def tarea(nombre, pasos):
    for i in range(1, pasos + 1):
        print(f'  [{nombre}] paso {i}/{pasos}')
        await asyncio.sleep(0)      # cede el control, como el yield


async def main_41():
    await asyncio.gather(tarea('A', 3), tarea('B', 2), tarea('C', 4))


def parte_41():
    print("=== 4.1 el equivalente con asyncio ===")
    asyncio.run(main_41())

    # Punto 2: olvidarse del await delante de gather
    async def sin_await():
        asyncio.gather(tarea('X', 1))       # sin await
        print('  main termino sin esperar a nadie')
    print("  --- gather SIN await ---")
    asyncio.run(sin_await())

    # Punto 3: asyncio.run() dos veces seguidas
    print("  --- asyncio.run() dos veces seguidas ---")
    asyncio.run(tarea('P', 1))
    asyncio.run(tarea('Q', 1))
    print("  las dos corrieron: cada run() crea y cierra su propio loop")

    # Punto 3b: run() adentro de una corrutina que ya esta corriendo
    async def anidado():
        try:
            asyncio.run(tarea('R', 1))
        except RuntimeError as e:
            print(f"  run() adentro de un loop -> RuntimeError: {e}")
    asyncio.run(anidado())
    print()


# ---- 4.2 Crear no es ejecutar ----

def parte_42():
    print("=== 4.2 crear no es ejecutar ===")

    async def saludar():
        print('  hola')

    import warnings
    with warnings.catch_warnings(record=True) as capturados:
        warnings.simplefilter("always")
        c = saludar()                   # no imprime nada
        print(f"  saludar() devolvio: {type(c).__name__} (no imprimio nada)")
        del c
        import gc
        gc.collect()
        for w in capturados:
            print(f"  aviso: {w.category.__name__}: {w.message}")

    print("  con asyncio.run():")
    asyncio.run(saludar())
    print()


# ---- 4.3 gather ----

async def dormilona(nombre, segundos):
    await asyncio.sleep(segundos)
    print(f'  [{nombre}] termine tras {segundos}s')
    return nombre


async def main_43():
    print("  orden de TERMINACION:")
    resultados = await asyncio.gather(
        dormilona('lenta', 0.3), dormilona('rapida', 0.1),
        dormilona('media', 0.2))
    print(f"  orden de los RESULTADOS: {resultados}")
    print("  -> gather devuelve en el orden en que se PASARON, no en el "
          "que terminaron")


async def comparar_gather():
    print("  --- gather vs await secuencial (3 corrutinas de 1s) ---")
    inicio = time.perf_counter()
    await asyncio.gather(asyncio.sleep(1), asyncio.sleep(1), asyncio.sleep(1))
    print(f"    gather:      {time.perf_counter() - inicio:.2f}s")

    inicio = time.perf_counter()
    for _ in range(3):
        await asyncio.sleep(1)
    print(f"    secuencial:  {time.perf_counter() - inicio:.2f}s")


def parte_43():
    print("=== 4.3 gather ===")
    asyncio.run(main_43())
    asyncio.run(comparar_gather())
    print()


if __name__ == "__main__":
    parte_41()
    parte_42()
    parte_43()
