"""Analizador Resumen: PID/PPID/usuario/estado/threads/CPU%/comando.

CPU% se calcula por delta entre dos llamadas a recolectar(), que están
separadas por el intervalo del analizador. Por eso el recolector guarda estado
(jiffies previos + timestamp) en un closure que vive lo que vive el proceso.
"""
import time

import procfs


def crear_recolector(verbose):
    prev = {}          # {pid: jiffies_cpu}
    prev_t = [None]    # lista de 1 elem para poder reasignar dentro del closure

    def recolectar():
        ahora = time.time()
        dt = (ahora - prev_t[0]) if prev_t[0] else None
        nuevos = {}
        procesos = []

        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                status = procfs.leer_status(pid)
                jiffies = st["utime"] + st["stime"]
                nuevos[pid] = jiffies

                cpu = 0.0
                if dt and pid in prev:
                    cpu = (jiffies - prev[pid]) / procfs.CLK_TCK / dt * 100

                uid = procfs.uid_de_status(status)
                procesos.append({
                    "pid": pid,
                    "ppid": st["ppid"],
                    "uid": uid,
                    "gid": procfs.gid_de_status(status),
                    "usuario": procfs.nombre_usuario(uid),
                    "estado": st["estado"],
                    "threads": st["num_threads"],
                    "cpu": round(cpu, 1),
                    "cmd": procfs.leer_cmdline(pid) or f"[{st['comm']}]",
                })
            except (FileNotFoundError, ProcessLookupError, KeyError, IndexError, ValueError):
                continue

        prev.clear()
        prev.update(nuevos)
        prev_t[0] = ahora
        procesos.sort(key=lambda p: p["cpu"], reverse=True)
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
