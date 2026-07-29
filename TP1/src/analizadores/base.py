"""Loop genérico de un analizador (Día 2: esqueleto con datos de prueba).

Cada analizador es un PROCESO independiente (no thread). Todos corren el mismo
loop `correr()`, parametrizado por:
  - nombre: la clave que le toca en el snapshot ('resumen', 'memoria', ...).
  - snapshot: el Manager().dict() compartido.
  - lock: lock compartido (ver nota abajo sobre cuándo hace falta).
  - intervalo: un multiprocessing.Value('d') con el período de refresco. Se
    relee en CADA vuelta, así el display puede ajustarlo en vivo con +/-.
  - recolectar: callable() -> dict con los datos de esta dimensión.

Mañana, cada analizador real va a pasar su propio `recolectar`; el loop no cambia.
"""
import os
import time


def correr(nombre, snapshot, lock, intervalo, recolectar):
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
    """Fábrica de un `recolectar` de prueba para el Día 2.

    Devuelve un contador incremental + el PID del proceso analizador, así en el
    supervisor vemos que el snapshot se actualiza y sabemos qué PID matar en la
    prueba de kill -9. Mañana esto lo reemplaza la lectura real de /proc.
    """
    estado = {"n": 0}

    def recolectar():
        estado["n"] += 1
        return {"muestra": estado["n"], "pid_analizador": os.getpid()}

    return recolectar
