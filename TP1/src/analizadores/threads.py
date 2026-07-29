"""Analizador Threads: LWPs de cada proceso (task/), con CPU% y ctx switches.

Igual que resumen, la CPU por thread es un delta de jiffies entre llamadas, así
que guardamos los jiffies previos por (pid, tid).
"""
import time

import procfs


def crear_recolector(verbose):
    prev = {}          # {(pid, tid): jiffies}
    prev_t = [None]

    def recolectar():
        ahora = time.time()
        dt = (ahora - prev_t[0]) if prev_t[0] else None
        nuevos = {}
        procesos = []

        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                hilos_raw = procfs.leer_threads(pid)
            except procfs.ERRORES_PROC:
                continue

            hilos = []
            for h in hilos_raw:
                clave = (pid, h["tid"])
                nuevos[clave] = h["jiffies"]
                cpu = 0.0
                if dt and clave in prev:
                    cpu = (h["jiffies"] - prev[clave]) / procfs.CLK_TCK / dt * 100
                hilos.append({
                    "tid": h["tid"],
                    "comm": h["comm"],
                    "estado": h["estado"],
                    "cpu": round(cpu, 1),
                    "ctx_vol": h["ctx_vol"],
                    "ctx_inv": h["ctx_inv"],
                })
            procesos.append({"pid": pid, "comm": st["comm"], "hilos": hilos})

        prev.clear()
        prev.update(nuevos)
        prev_t[0] = ahora
        procesos.sort(key=lambda p: len(p["hilos"]), reverse=True)
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
