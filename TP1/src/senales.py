"""Manejo de las señales que recibe EL MONITOR (no confundir con el analizador
analizadores/senales.py, que lee las señales de OTROS procesos).

Versión pragmática del self-pipe: en lugar de escribir a un pipe real, el
handler solo pone en True un flag booleano (asignar un atributo es una operación
simple, no toma locks ni hace I/O => razonablemente segura dentro de un handler).
El loop principal lee esos flags en cada iteración y ahí sí ejecuta la acción
real (releer config, volcar el snapshot, etc.), que puede ser "pesada".

Por qué NO hacemos el trabajo dentro del handler: un handler puede interrumpir
al programa en cualquier punto, incluso mientras tiene tomado un lock o está en
medio de un malloc. Si adentro del handler tomamos ese mismo lock o pedimos
memoria, deadlock o corrupción. La regla async-signal-safe es: tocar lo mínimo
(un flag) y salir.
"""
import signal


class EstadoSenales:
    """Flags que el handler prende y el loop principal apaga tras actuar."""
    def __init__(self):
        self.salir = False
        self.recargar = False
        self.dump = False
        self.toggle_verbose = False


def instalar(estado):
    """Registra los handlers. Cada uno solo prende su flag."""
    def hacer(attr):
        def handler(signum, frame):
            setattr(estado, attr, True)
        return handler

    signal.signal(signal.SIGINT, hacer("salir"))
    signal.signal(signal.SIGTERM, hacer("salir"))
    signal.signal(signal.SIGHUP, hacer("recargar"))
    signal.signal(signal.SIGUSR1, hacer("dump"))
    signal.signal(signal.SIGUSR2, hacer("toggle_verbose"))
    # SIGWINCH (repintar al redimensionar) es opcional: lo dejamos para el Día 5
    # junto con la TUI, cuando haya una pantalla real que repintar.
