"""Día 4 — TUI del monitor (rich).

Corre en el proceso principal (el mismo que maneja señales). Lee el snapshot
compartido y lo renderiza: una lista de procesos arriba + un panel de detalle
abajo que cambia según la vista activa.

La lectura de teclado es NO bloqueante y va en un thread aparte (permitido por
la consigna para el proceso de display). El thread solo muta el estado de la UI;
el loop principal lee ese estado y redibuja. Ese estado lo protege un lock chico
porque hay dos threads tocándolo (el de teclado escribe, el principal lee).
"""
import os
import select
import sys
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# tecla -> vista (número y letra mnemotécnica)
VISTAS = {
    "1": "resumen", "r": "resumen",
    "2": "memoria", "m": "memoria",
    "3": "fds", "f": "fds",
    "4": "threads", "t": "threads",
    "5": "senales", "s": "senales",
    "6": "scheduling", "p": "scheduling",
    "7": "sistema", "g": "sistema",
}
TITULOS = {
    "resumen": "1·Resumen", "memoria": "2·Memoria", "fds": "3·FDs",
    "threads": "4·Threads", "senales": "5·Señales", "scheduling": "6·Scheduling",
    "sistema": "7·Sistema",
}
# intervalos mínimos por vista (consigna); el máximo lo fijamos nosotros
MIN_INT = {"resumen": 0.5, "memoria": 1.0, "fds": 2.0, "threads": 0.5,
           "senales": 5.0, "scheduling": 5.0, "sistema": 1.0}
MAX_INT = 60.0
PASO_INT = 0.5

ALTO_LISTA = 12  # filas visibles de la lista de procesos


class LectorTeclado(threading.Thread):
    """Lee stdin en crudo y traduce a teclas lógicas (UP, ENTER, 'q', ...)."""
    def __init__(self, on_key):
        super().__init__(daemon=True)
        self.on_key = on_key
        self._stop = threading.Event()

    def run(self):
        fd = sys.stdin.fileno()
        while not self._stop.is_set():
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            ch = os.read(fd, 1)
            if not ch:
                break
            b = ch[0]
            if b == 0x1b:  # ESC: puede ser una flecha (ESC [ A/B/C/D)
                r2, _, _ = select.select([sys.stdin], [], [], 0.01)
                seq = os.read(fd, 2) if r2 else b""
                self.on_key({b"[A": "UP", b"[B": "DOWN",
                             b"[C": "RIGHT", b"[D": "LEFT"}.get(seq, "ESC"))
            elif b in (10, 13):
                self.on_key("ENTER")
            elif b == 127:
                self.on_key("BACKSPACE")
            else:
                self.on_key(chr(b))

    def detener(self):
        self._stop.set()


class Display:
    def __init__(self, snapshot, componentes, verbose, estado, nombres):
        self.snapshot = snapshot
        self.componentes = componentes   # {nombre: (Process, Value_intervalo)}
        self.verbose = verbose
        self.estado = estado             # EstadoSenales (para salir por 'q' o señal)
        self.nombres = nombres

        self.vista = "resumen"
        self.idx = 0
        self.pin = None                  # pid pineado
        self.orden = "cpu"               # cpu | rss | pid
        self.filtro_cmd = ""
        self.filtro_user = ""
        self.ayuda = False
        self.modo_input = None           # None | 'cmd' | 'user'
        self.buffer = ""
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Teclado
    # ------------------------------------------------------------------ #
    def on_key(self, k):
        if k is None:
            return
        with self._lock:
            if self.modo_input:
                self._key_input(k)
                return

            if k in VISTAS:
                self.vista = VISTAS[k]
            elif k == "UP":
                self.idx -= 1
            elif k == "DOWN":
                self.idx += 1
            elif k == "ENTER":
                self._toggle_pin()
            elif k == "/":
                self.modo_input, self.buffer = "cmd", ""
            elif k == "u":
                self.modo_input, self.buffer = "user", ""
            elif k == "c":
                self.orden = {"cpu": "rss", "rss": "pid", "pid": "cpu"}[self.orden]
            elif k in ("+", "-"):
                self._ajustar_intervalo(k)
            elif k in ("h", "?"):
                self.ayuda = not self.ayuda
            elif k == "ESC":
                self.ayuda = False
            elif k == "q":
                self.estado.salir = True

    def _key_input(self, k):
        if k == "ENTER":
            if self.modo_input == "cmd":
                self.filtro_cmd = self.buffer.strip()
            else:
                self.filtro_user = self.buffer.strip()
            self.modo_input, self.buffer = None, ""
        elif k == "ESC":
            self.modo_input, self.buffer = None, ""
        elif k == "BACKSPACE":
            self.buffer = self.buffer[:-1]
        elif len(k) == 1 and k.isprintable():
            self.buffer += k

    def _toggle_pin(self):
        filas = self._filas_lista()
        if not filas:
            return
        i = max(0, min(self.idx, len(filas) - 1))
        pid = filas[i]["pid"]
        self.pin = None if self.pin == pid else pid

    def _ajustar_intervalo(self, k):
        _, intervalo = self.componentes[self.vista]
        if k == "+":
            intervalo.value = min(MAX_INT, intervalo.value + PASO_INT)
        else:
            intervalo.value = max(MIN_INT[self.vista], intervalo.value - PASO_INT)

    # ------------------------------------------------------------------ #
    # Datos
    # ------------------------------------------------------------------ #
    def _leer(self, nombre):
        """Devuelve (datos, ts) de una clave del snapshot."""
        entrada = self.snapshot[nombre]
        return entrada["datos"], entrada["ts"]

    def _filas_lista(self):
        """Lista de procesos para la tabla de arriba (resumen + RSS de memoria),
        ya filtrada y ordenada."""
        resumen, _ = self._leer("resumen")
        memoria, _ = self._leer("memoria")
        rss_por_pid = {}
        for p in (memoria.get("procesos", []) if memoria else []):
            rss_por_pid[p["pid"]] = (p["vm"].get("VmRSS") or 0)

        filas = []
        for p in (resumen.get("procesos", []) if resumen else []):
            fila = dict(p)
            fila["rss"] = rss_por_pid.get(p["pid"], 0)
            filas.append(fila)

        if self.filtro_cmd:
            f = self.filtro_cmd.lower()
            filas = [x for x in filas if f in x["cmd"].lower()]
        if self.filtro_user:
            f = self.filtro_user.lower()
            filas = [x for x in filas if f in str(x["usuario"]).lower()]

        if self.orden == "cpu":
            filas.sort(key=lambda x: x["cpu"], reverse=True)
        elif self.orden == "rss":
            filas.sort(key=lambda x: x["rss"], reverse=True)
        else:
            filas.sort(key=lambda x: x["pid"])
        return filas

    def _proc_de_vista(self, nombre, pid):
        datos, _ = self._leer(nombre)
        for p in (datos.get("procesos", []) if datos else []):
            if p["pid"] == pid:
                return p
        return None

    # ------------------------------------------------------------------ #
    # Render
    # ------------------------------------------------------------------ #
    def render(self):
        with self._lock:
            filas = self._filas_lista()

            # resolver selección: el pin manda si sigue presente
            sel = max(0, min(self.idx, len(filas) - 1)) if filas else 0
            if self.pin is not None:
                for i, x in enumerate(filas):
                    if x["pid"] == self.pin:
                        sel = i
                        break
            self.idx = sel

            pid_sel = filas[sel]["pid"] if filas else None
            partes = [self._cabecera(len(filas)), self._tabla_lista(filas, sel)]
            if self.ayuda:
                partes.append(self._panel_ayuda())
            else:
                partes.append(self._panel_detalle(pid_sel))
            partes.append(self._pie())
            return Group(*partes)

    def _cabecera(self, n):
        _, intervalo = self.componentes[self.vista]
        _, ts = self._leer(self.vista)
        edad = (time.time() - ts) if ts else float("inf")
        filtros = []
        if self.filtro_cmd:
            filtros.append(f"cmd~'{self.filtro_cmd}'")
        if self.filtro_user:
            filtros.append(f"user~'{self.filtro_user}'")
        txt = (f"[b]MONITOR[/b]  vista=[b cyan]{TITULOS[self.vista]}[/b cyan]  "
               f"cada={intervalo.value:.1f}s (dato hace {edad:.1f}s)  "
               f"orden={self.orden}  verbose={'ON' if self.verbose.value else 'OFF'}  "
               f"procs={n}")
        if filtros:
            txt += "  filtros: " + " ".join(filtros)
        if self.pin is not None:
            txt += f"  📌pin={self.pin}"
        return Panel(txt, style="white on grey19", expand=True)

    def _tabla_lista(self, filas, sel):
        t = Table(expand=True, pad_edge=False)
        for col, just in (("PID", "right"), ("USUARIO", "left"), ("S", "center"),
                          ("CPU%", "right"), ("RSS(kB)", "right"),
                          ("THR", "right"), ("COMANDO", "left")):
            t.add_column(col, justify=just, no_wrap=True)

        if not filas:
            t.add_row("—", "—", "—", "—", "—", "—", "(sin datos / filtro vacío)")
            return t

        # ventana visible centrada en la selección
        ini = max(0, min(sel - ALTO_LISTA // 2, len(filas) - ALTO_LISTA))
        ini = max(0, ini)
        for i in range(ini, min(ini + ALTO_LISTA, len(filas))):
            x = filas[i]
            marca = "›" if i == sel else " "
            pin = "📌" if x["pid"] == self.pin else ""
            estilo = "reverse" if i == sel else None
            t.add_row(f"{marca}{x['pid']}{pin}", str(x["usuario"]), x["estado"],
                      f"{x['cpu']:.1f}", f"{x['rss']:,}", str(x["threads"]),
                      x["cmd"][:60], style=estilo)
        return t

    def _panel_detalle(self, pid):
        vista = self.vista
        if vista == "sistema":
            return self._detalle_sistema()
        if pid is None:
            return Panel(Text("Sin proceso seleccionado."), title=TITULOS[vista])

        cuerpo = {
            "resumen": self._detalle_resumen,
            "memoria": self._detalle_memoria,
            "fds": self._detalle_fds,
            "threads": self._detalle_threads,
            "senales": self._detalle_senales,
            "scheduling": self._detalle_scheduling,
        }[vista](pid)
        return Panel(cuerpo, title=f"{TITULOS[vista]} · PID {pid}", expand=True)

    def _detalle_resumen(self, pid):
        p = self._proc_de_vista("resumen", pid)
        if not p:
            return Text("(proceso ya no está)")
        return Text(
            f"PID {p['pid']}   PPID {p['ppid']}   UID {p.get('uid','?')}  "
            f"GID {p.get('gid','?')}   usuario {p['usuario']}\n"
            f"estado {p['estado']}   threads {p['threads']}   CPU {p['cpu']}%\n"
            f"cmd: {p['cmd']}")

    def _detalle_memoria(self, pid):
        p = self._proc_de_vista("memoria", pid)
        if not p:
            return Text("(proceso ya no está)")
        vm = p["vm"]
        linea1 = "   ".join(f"{k}={vm[k]}" for k in
                            ("VmSize", "VmRSS", "VmHWM", "VmData", "VmStk", "VmExe", "VmLib", "VmSwap")
                            if vm.get(k) is not None)
        t = Table(title=None, expand=True)
        for c in ("segmento", "count", "kB"):
            t.add_column(c, justify="right" if c != "segmento" else "left")
        for seg, info in (p.get("segmentos") or {}).items():
            t.add_row(seg, str(info["count"]), f"{info['kb']:,}")
        return Group(Text(linea1),
                     Text(f"page faults: minor={p['minflt']}  major={p['majflt']}"), t)

    def _detalle_fds(self, pid):
        p = self._proc_de_vista("fds", pid)
        if not p:
            return Text("(proceso ya no está)")
        if p.get("error"):
            return Text(f"({p['error']})")
        t = Table(expand=True)
        for c, j in (("FD", "right"), ("tipo", "left"), ("destino", "left")):
            t.add_column(c, justify=j, no_wrap=(c != "destino"))
        for fd in p["lista"]:
            t.add_row(str(fd["fd"]), fd["tipo"], fd["destino"][:70])
        resumen_tipos = "  ".join(f"{k}:{v}" for k, v in p["por_tipo"].items())
        return Group(Text(f"total FDs: {p['total']}   ({resumen_tipos})"), t)

    def _detalle_threads(self, pid):
        p = self._proc_de_vista("threads", pid)
        if not p:
            return Text("(proceso ya no está)")
        t = Table(expand=True)
        for c, j in (("TID", "right"), ("nombre", "left"), ("S", "center"),
                     ("CPU%", "right"), ("ctx.vol", "right"), ("ctx.inv", "right")):
            t.add_column(c, justify=j, no_wrap=True)
        for h in p["hilos"]:
            t.add_row(str(h["tid"]), h["comm"], h["estado"], f"{h['cpu']:.1f}",
                      str(h["ctx_vol"]), str(h["ctx_inv"]))
        return Group(Text(f"{len(p['hilos'])} threads (LWPs)"), t)

    def _detalle_senales(self, pid):
        p = self._proc_de_vista("senales", pid)
        if not p:
            return Text("(proceso ya no está)")
        etiquetas = {
            "bloqueadas": "SigBlk (bloqueadas)", "ignoradas": "SigIgn (ignoradas)",
            "capturadas": "SigCgt (con handler)", "pendientes": "SigPnd (pendientes)",
            "pendientes_grupo": "ShdPnd (pend. grupo)",
        }
        lineas = []
        for clave, etiqueta in etiquetas.items():
            nombres = p.get(clave, [])
            lineas.append(f"{etiqueta}: {', '.join(nombres) if nombres else '—'}")
        return Text("\n".join(lineas))

    def _detalle_scheduling(self, pid):
        p = self._proc_de_vista("scheduling", pid)
        if not p:
            return Text("(proceso ya no está)")
        return Text(
            f"nice {p['nice']}   priority {p['priority']}   policy {p['policy']}   "
            f"RT prio {p['rt_priority']}\n"
            f"affinity CPUs: {p['affinity']}\n"
            f"ctx switches: voluntarios={p['ctx_vol']}  involuntarios={p['ctx_inv']}\n"
            f"utime {p['utime']}  stime {p['stime']}   SID {p['sid']}  PGID {p['pgid']}")

    def _detalle_sistema(self):
        d, ts = self._leer("sistema")
        if not d:
            return Panel(Text("Esperando datos del sistema..."), title=TITULOS["sistema"])
        c = d.get("cpu", {})
        mem = d.get("memoria", {})
        estados = "  ".join(f"{k}:{v}" for k, v in d.get("conteo_estados", {}).items())
        top_cpu = "  ".join(f"{comm}({cpu}%)" for cpu, _, comm in d.get("top_cpu", []))
        top_mem = "  ".join(f"{comm}({rss}kB)" for rss, _, comm in d.get("top_mem", []))
        cuerpo = Text(
            f"CPU: user {c.get('user','?')}%  system {c.get('system','?')}%  "
            f"idle {c.get('idle','?')}%  iowait {c.get('iowait','?')}%\n"
            f"load: {d.get('load')}   uptime: {d.get('uptime')}s\n"
            f"mem: total {mem.get('MemTotal')}kB  free {mem.get('MemFree')}kB  "
            f"cached {mem.get('Cached')}kB  swap {mem.get('SwapTotal')}kB\n"
            f"procesos: {d.get('procesos_total')} ({estados})   "
            f"threads: {d.get('threads_total')}   zombies: {d.get('zombies')}\n"
            f"top CPU: {top_cpu}\n"
            f"top MEM: {top_mem}")
        return Panel(cuerpo, title=TITULOS["sistema"], expand=True)

    def _panel_ayuda(self):
        ayuda = (
            "1-7 / r m f t s p g : cambiar vista\n"
            "↑ ↓ : navegar     Enter : pin/unpin del proceso\n"
            "/ : filtrar por comando     u : filtrar por usuario\n"
            "c : ciclar orden (cpu/rss/pid)     + - : ajustar intervalo de la vista\n"
            "h ? : ayuda     q : salir limpio")
        return Panel(Text(ayuda), title="Ayuda", expand=True)

    def _pie(self):
        if self.modo_input:
            etiqueta = "filtrar comando" if self.modo_input == "cmd" else "filtrar usuario"
            return Panel(Text(f"{etiqueta}: {self.buffer}▌  (Enter=aceptar, Esc=cancelar)"),
                         style="black on yellow")
        return Text("  [dim]1-7 vistas · ↑↓ navegar · Enter pin · / cmd · u user · "
                    "c orden · +/- intervalo · h ayuda · q salir[/dim]",
                    justify="center")

    # ------------------------------------------------------------------ #
    def run(self, procesar_senales):
        es_tty = sys.stdin.isatty()
        old = None
        lector = None
        if es_tty:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            tty.setcbreak(fd)   # cbreak (no raw): deja ISIG activo => Ctrl+C sigue disparando SIGINT
            lector = LectorTeclado(self.on_key)
            lector.start()

        console = Console()
        try:
            with Live(self.render(), console=console, screen=es_tty,
                      auto_refresh=False) as live:
                while not self.estado.salir:
                    procesar_senales()
                    live.update(self.render(), refresh=True)
                    time.sleep(0.1)
        finally:
            if lector:
                lector.detener()
            if old is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
