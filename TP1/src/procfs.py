"""Helpers para leer y parsear /proc en Linux.

Toda la lectura del kernel del monitor pasa por acá. Las funciones son "tontas":
abren un archivo de /proc, lo parsean y devuelven datos Python. La lógica de
"cada cuánto" y "qué hago con esto" vive en los analizadores.
"""
import os
import pwd
import signal as _signal

# jiffies por segundo (casi siempre 100). Es la unidad de utime/stime en stat.
CLK_TCK = os.sysconf("SC_CLK_TCK")

# Mapa número_de_señal -> nombre ('SIGINT', ...). Se arma UNA vez al importar
# el módulo y se reusa para decodificar todas las máscaras (SigBlk, etc.).
TABLA_SENALES = {s.value: s.name for s in _signal.Signals}

# Política de scheduling: campo 41 de stat es un número; lo pasamos a nombre.
POLITICAS_SCHED = {0: "OTHER", 1: "FIFO", 2: "RR", 3: "BATCH", 5: "IDLE", 6: "DEADLINE"}

# Errores esperables al leer /proc de un proceso puntual; el analizador lo saltea
# en vez de caerse. Cubre: el proceso desapareció (FileNotFound/ProcessLookup),
# está protegido y no somos su dueño ni root (Permission), o una lectura devolvió
# algo inesperado (Key/Index/Value). Un único lugar para que los 7 sean iguales.
ERRORES_PROC = (FileNotFoundError, ProcessLookupError, PermissionError,
                KeyError, IndexError, ValueError)


# --------------------------------------------------------------------------- #
# Básico (Día 1)
# --------------------------------------------------------------------------- #
def listar_pids():
    """PIDs actuales: las carpetas cuyo nombre es un número en /proc."""
    return [int(nombre) for nombre in os.listdir("/proc") if nombre.isdigit()]


def leer_stat(pid):
    """Parsea /proc/<pid>/stat.

    `comm` viene entre paréntesis y puede tener espacios/paréntesis, así que un
    split() directo rompe: buscamos el primer '(' y el ÚLTIMO ')' y parseamos por
    posición lo que sigue. `resto[i]` == campo (i+3) de proc(5).
    """
    with open(f"/proc/{pid}/stat") as f:
        contenido = f.read()

    ini = contenido.index("(")
    fin = contenido.rindex(")")
    comm = contenido[ini + 1:fin]
    resto = contenido[fin + 1:].split()

    return {
        "pid": pid,
        "comm": comm,
        "estado": resto[0],            # campo 3
        "ppid": int(resto[1]),         # campo 4
        "pgid": int(resto[2]),         # campo 5
        "sid": int(resto[3]),          # campo 6
        "minflt": int(resto[7]),       # campo 10
        "majflt": int(resto[9]),       # campo 12
        "utime": int(resto[11]),       # campo 14
        "stime": int(resto[12]),       # campo 15
        "priority": int(resto[15]),    # campo 18
        "nice": int(resto[16]),        # campo 19
        "num_threads": int(resto[17]),  # campo 20
        "starttime": int(resto[19]),   # campo 22
        "rt_priority": int(resto[37]),  # campo 40
        "policy": int(resto[38]),      # campo 41
    }


def _parsear_status(f):
    datos = {}
    for linea in f:
        clave, sep, valor = linea.partition(":")
        if sep:
            datos[clave] = valor.strip()
    return datos


def leer_status(pid):
    """Parsea /proc/<pid>/status (formato `Clave:\\tvalor`)."""
    with open(f"/proc/{pid}/status") as f:
        return _parsear_status(f)


def leer_cmdline(pid):
    """Línea de comando completa. Los args se separan con '\\0', no espacios.
    Vacío => kernel thread (sin cmdline): devolvemos "" y el caller usa [comm]."""
    with open(f"/proc/{pid}/cmdline", "rb") as f:
        crudo = f.read()
    if crudo:
        return crudo.replace(b"\x00", b" ").strip().decode(errors="replace")
    return ""


def uid_de_status(status):
    """UID real (primer campo de `Uid: real efec saved fs`)."""
    return int(status["Uid"].split()[0])


def gid_de_status(status):
    """GID real (primer campo de `Gid: real efec saved fs`)."""
    return int(status["Gid"].split()[0])


def nombre_usuario(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


# --------------------------------------------------------------------------- #
# Memoria (Día 3)
# --------------------------------------------------------------------------- #
def _kb(status, clave):
    """Toma 'VmRSS' -> '1234 kB' del status y devuelve el int 1234 (o None)."""
    valor = status.get(clave)
    if not valor:
        return None
    return int(valor.split()[0])


def leer_memoria_vm(status):
    """Campos Vm* de /proc/<pid>/status, en kB (None si el proceso no los tiene,
    ej: kernel threads)."""
    return {clave: _kb(status, clave) for clave in
            ("VmSize", "VmRSS", "VmData", "VmStk", "VmExe", "VmLib", "VmHWM", "VmSwap")}


def leer_maps(pid):
    """Agrupa /proc/<pid>/maps en segmentos por permisos y etiqueta.

    Reglas de agrupación (en orden): [heap] y [stack] por su etiqueta; 's' en los
    permisos => mapeo compartido; 'x' => código ejecutable (text); el resto, data.
    Devuelve {categoria: {"count": n, "kb": total}}.
    """
    grupos = {c: {"count": 0, "kb": 0} for c in ("text", "data", "heap", "stack", "shared")}
    with open(f"/proc/{pid}/maps") as f:
        for linea in f:
            partes = linea.split(maxsplit=5)
            rango, perms = partes[0], partes[1]
            ruta = partes[5].strip() if len(partes) > 5 else ""

            ini, fin = rango.split("-")
            tam_kb = (int(fin, 16) - int(ini, 16)) // 1024

            if ruta == "[heap]":
                cat = "heap"
            elif ruta == "[stack]":
                cat = "stack"
            elif "s" in perms:
                cat = "shared"
            elif "x" in perms:
                cat = "text"
            else:
                cat = "data"

            grupos[cat]["count"] += 1
            grupos[cat]["kb"] += tam_kb
    return grupos


# --------------------------------------------------------------------------- #
# File descriptors (Día 3)
# --------------------------------------------------------------------------- #
def tipo_fd(destino):
    """Infiere el tipo de un FD a partir del destino del symlink."""
    if destino.startswith("socket:"):
        return "socket"
    if destino.startswith("pipe:"):
        return "pipe"
    if destino.startswith("anon_inode:"):
        return "anon"
    if destino.startswith("/dev/pts") or destino.startswith("/dev/tty"):
        return "tty"
    if destino.startswith("/"):
        return "file"
    return "otro"


def leer_fds(pid, limite=None):
    """FDs abiertos de un proceso vía os.listdir + os.readlink.
    `limite` acota cuántos se detallan en la lista (los contamos todos igual)."""
    ruta = f"/proc/{pid}/fd"
    res = {"total": 0, "por_tipo": {}, "lista": []}
    for nombre in os.listdir(ruta):
        try:
            destino = os.readlink(f"{ruta}/{nombre}")
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue  # el FD se cerró entre el listdir y el readlink
        t = tipo_fd(destino)
        res["total"] += 1
        res["por_tipo"][t] = res["por_tipo"].get(t, 0) + 1
        if limite is None or len(res["lista"]) < limite:
            res["lista"].append({"fd": int(nombre), "destino": destino, "tipo": t})
    return res


# --------------------------------------------------------------------------- #
# Threads / LWPs (Día 3)
# --------------------------------------------------------------------------- #
def leer_threads(pid):
    """Un dict por thread (LWP) del proceso, desde /proc/<pid>/task/<tid>/.
    'jiffies' es acumulado; el delta de CPU lo calcula el analizador."""
    base = f"/proc/{pid}/task"
    hilos = []
    for tid in os.listdir(base):
        try:
            with open(f"{base}/{tid}/stat") as f:
                contenido = f.read()
            resto = contenido[contenido.rindex(")") + 1:].split()
            with open(f"{base}/{tid}/comm") as f:
                comm = f.read().strip()
            with open(f"{base}/{tid}/status") as f:
                st = _parsear_status(f)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
        hilos.append({
            "tid": int(tid),
            "comm": comm,
            "estado": resto[0],
            "jiffies": int(resto[11]) + int(resto[12]),
            "ctx_vol": int(st.get("voluntary_ctxt_switches", 0)),
            "ctx_inv": int(st.get("nonvoluntary_ctxt_switches", 0)),
        })
    return hilos


# --------------------------------------------------------------------------- #
# Señales (info) (Día 3)
# --------------------------------------------------------------------------- #
def decodificar_mascara(hexstr):
    """Convierte una máscara hex de 64 bits (SigBlk/SigIgn/...) a nombres.
    El bit i (0-based) representa la señal (i+1)."""
    valor = int(hexstr, 16)
    nombres = []
    for i in range(64):
        if valor & (1 << i):
            num = i + 1
            nombres.append(TABLA_SENALES.get(num, f"SIG{num}"))
    return nombres


# --------------------------------------------------------------------------- #
# Sistema global (Día 3)
# --------------------------------------------------------------------------- #
def leer_cpu_global():
    """Línea 'cpu' de /proc/stat: [user, nice, system, idle, iowait, ...] en jiffies."""
    with open("/proc/stat") as f:
        for linea in f:
            if linea.startswith("cpu "):
                return [int(x) for x in linea.split()[1:]]
    return []


def leer_btime():
    """Boot time (epoch) de la línea 'btime' de /proc/stat."""
    with open("/proc/stat") as f:
        for linea in f:
            if linea.startswith("btime"):
                return int(linea.split()[1])
    return 0


def leer_meminfo():
    """/proc/meminfo como {clave: kB}."""
    datos = {}
    with open("/proc/meminfo") as f:
        for linea in f:
            clave, _, resto = linea.partition(":")
            datos[clave] = int(resto.split()[0])
    return datos


def leer_loadavg():
    with open("/proc/loadavg") as f:
        p = f.read().split()
    return [float(p[0]), float(p[1]), float(p[2])]


def leer_uptime():
    with open("/proc/uptime") as f:
        return float(f.read().split()[0])
