"""Loop común que corre cada analizador (un PROCESO independiente por vista).

Todos los analizadores comparten este loop `correr()`; lo único que cambia entre
ellos es la función `recolectar(pids)` que se les pasa. Parámetros:
  - nombre: la clave que le toca en el snapshot ('resumen', 'memoria', ...).
  - snapshot: el Manager().dict() compartido.
  - lock: lock compartido (ver nota en el punto de escritura).
  - intervalo: un multiprocessing.Value('d') con el período de refresco. Se
    relee en CADA vuelta, así el display puede ajustarlo en vivo con +/-.
  - recolectar: callable(pids) -> dict con los datos de esta dimensión.
  - cola_pids: la Queue por la que el Recolector le manda la lista de PIDs.
"""
import queue
import time


def _ultima_lista(cola, anterior):
    """Devuelve la última lista de PIDs que el recolector puso en la cola.

    Si es la primera vez, espera un poco a que llegue. Si la cola está vacía pero
    ya teníamos una lista de antes, reusamos esa (la lista de procesos no cambia
    tan rápido, no pasa nada si es de hace un segundo).
    """
    nueva = anterior
    if not anterior:
        try:
            nueva = cola.get(timeout=2)      # primera vez: esperamos al recolector
        except queue.Empty:
            return anterior
    # El recolector puede haber dejado varias listas; nos quedamos con la última.
    while True:
        try:
            nueva = cola.get_nowait()
        except queue.Empty:
            break
    return nueva


def correr(nombre, snapshot, lock, intervalo, recolectar, cola_pids):
    # Ciclo de vida del analizador: recibir los PIDs del recolector -> recolectar
    # sus datos -> publicar en el snapshot -> dormir el intervalo, para siempre.
    pids = []
    while True:
        pids = _ultima_lista(cola_pids, pids)
        datos = recolectar(pids)

        # --- ACÁ EL ANALIZADOR GUARDA SUS DATOS EN EL SNAPSHOT ----------
        # Guardamos el diccionario ENTERO de una vez. No lo modificamos por
        # partes porque el Manager.dict no se entera de los cambios hechos
        # ADENTRO de un dict que ya estaba guardado. En criollo:
        #   snapshot[nombre]["datos"] = x   -> NO se comparte con los otros procesos
        #   snapshot[nombre] = {...todo...}  -> SÍ (reemplazamos la clave completa)
        #
        # ¿Para qué el lock? Entre los analizadores NO hace falta: cada uno escribe
        # SOLO su propia clave (nunca dos tocan la misma), así que no se pisan. El
        # lock sirve para el dump de SIGUSR1 (volcar_dump en main.py): ahí se copian
        # las 7 claves juntas usando este mismo lock, para que ningún analizador
        # escriba en el medio y el archivo quede como una foto de un solo momento.
        # El display no usa el lock: lee de a una clave y redibuja muy seguido,
        # no vale la pena frenarlo.
        with lock:
            snapshot[nombre] = {"datos": datos, "ts": time.time()}
        # ---------------------------------------------------------------

        time.sleep(intervalo.value)  # dormimos el intervalo actual (se cambia en vivo con +/-)
