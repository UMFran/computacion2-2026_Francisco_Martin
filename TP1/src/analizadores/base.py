"""Loop común que corre cada analizador (un PROCESO independiente por vista).

Todos los analizadores comparten este loop `correr()`; lo único que cambia entre
ellos es la función `recolectar` que se les pasa. Parámetros:
  - nombre: la clave que le toca en el snapshot ('resumen', 'memoria', ...).
  - snapshot: el Manager().dict() compartido.
  - lock: lock compartido (ver nota en el punto de escritura).
  - intervalo: un multiprocessing.Value('d') con el período de refresco. Se
    relee en CADA vuelta, así el display puede ajustarlo en vivo con +/-.
  - recolectar: callable() -> dict con los datos de esta dimensión.
"""
import os
import time


def correr(nombre, snapshot, lock, intervalo, recolectar):
    # Ciclo de vida del analizador: recolectar -> publicar en el snapshot ->
    # dormir el intervalo, para siempre (hasta que el padre lo termine).
    while True:
        datos = recolectar()

        # --- PUNTO DE ESCRITURA COMPARTIDA -------------------------------
        # Reasignamos la CLAVE ENTERA (no mutamos in-place). Con Manager.dict,
        # `snapshot[nombre]["datos"] = x` NO se propaga: el proxy no ve la
        # mutación de un dict anidado. Hay que hacer `snapshot[nombre] = {...}`.
        #
        # Ese __setitem__ es atómico de por sí (viaja como un pedido único al
        # proceso servidor del Manager, que los serializa). Como cada analizador
        # escribe SOLO su propia clave, no hay race ENTRE analizadores aunque no
        # hubiera lock. Tomo el lock igual para darle un propósito real al LADO
        # LECTOR: el dump de SIGUSR1 (volcar_dump en main.py) toma este mismo lock
        # para copiar las 7 claves de una, sin que ningún analizador escriba en el
        # medio => foto coherente. El display NO lo toma (lee de a una clave, que
        # ya es atómica, y a 10 fps no vale la pena la contención).
        with lock:
            snapshot[nombre] = {"datos": datos, "ts": time.time()}
        # -----------------------------------------------------------------

        time.sleep(intervalo.value)  # .value lee el Value (protegido por su lock interno)


def stub_recolectar(nombre):
    """Fábrica de un `recolectar` de PRUEBA (datos ficticios), sin leer /proc.

    La usa dia2_lister.py para mostrar la arquitectura multiproceso "en crudo".
    Devuelve un contador incremental + el PID del proceso analizador, así se ve
    que el snapshot se actualiza y se sabe qué PID matar en la prueba de kill -9.
    """
    estado = {"n": 0}

    def recolectar():
        estado["n"] += 1
        return {"muestra": estado["n"], "pid_analizador": os.getpid()}

    return recolectar
