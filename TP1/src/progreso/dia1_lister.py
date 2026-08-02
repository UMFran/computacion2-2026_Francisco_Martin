"""Día 1 — Monitor de procesos (versión de UN SOLO proceso, sin multiprocessing).

Lista los procesos leyendo /proc y muestra la vista Resumen:
PID, PPID, USUARIO, ESTADO, THREADS, CPU%, COMANDO.

CPU%: no existe un archivo que diga "este proceso usa X%". Hay que calcularlo.
Se lee utime+stime (jiffies acumulados de CPU) en dos momentos separados por un
intervalo, se saca el delta, se pasa a segundos (delta / CLK_TCK) y se divide por
el intervalo real. 100% == un core saturado durante todo el intervalo.
"""
import time

import procfs


def tomar_muestra_cpu():
    """Foto {pid: jiffies_cpu_acumulados} de todos los procesos vivos."""
    muestra = {}
    for pid in procfs.listar_pids():
        try:
            st = procfs.leer_stat(pid)
            muestra[pid] = st["utime"] + st["stime"]
        except (FileNotFoundError, ProcessLookupError):
            # El proceso murió entre listar_pids() y abrir su stat. Es lo normal
            # en un sistema vivo: /proc cambia mientras lo recorrés. No es error.
            continue
    return muestra


def recolectar(intervalo=0.5):
    # Primera lectura de CPU, esperar, y recolectar todo con la segunda lectura.
    antes = tomar_muestra_cpu()
    time.sleep(intervalo)

    filas = []
    for pid in procfs.listar_pids():
        try:
            st = procfs.leer_stat(pid)
            status = procfs.leer_status(pid)

            cmd = procfs.leer_cmdline(pid) or f"[{st['comm']}]"
            uid = procfs.uid_de_status(status)

            jiffies_ahora = st["utime"] + st["stime"]
            delta = jiffies_ahora - antes.get(pid, jiffies_ahora)
            cpu = (delta / procfs.CLK_TCK) / intervalo * 100

            filas.append({
                "pid": pid,
                "ppid": st["ppid"],
                "usuario": procfs.nombre_usuario(uid),
                "estado": st["estado"],
                "threads": st["num_threads"],
                "cpu": cpu,
                "cmd": cmd,
            })
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (KeyError, ValueError, IndexError):
            # Un proceso puntual con formato inesperado no debe tumbar todo el
            # recolector: lo salteamos y seguimos con el resto.
            continue
    return filas


def imprimir(filas):
    filas.sort(key=lambda f: f["cpu"], reverse=True)
    print(f"{'PID':>7} {'PPID':>7} {'USUARIO':<10} {'S':<2} "
          f"{'THR':>4} {'CPU%':>6}  COMANDO")
    print("-" * 78)
    for f in filas:
        print(f"{f['pid']:>7} {f['ppid']:>7} {f['usuario']:<10} "
              f"{f['estado']:<2} {f['threads']:>4} {f['cpu']:>6.1f}  "
              f"{f['cmd'][:48]}")
    print(f"\nTotal: {len(filas)} procesos")


if __name__ == "__main__":
    imprimir(recolectar())
