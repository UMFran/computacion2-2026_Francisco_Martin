"""Analizador Sistema global: CPU%, load, memoria, conteo por estado, zombies,
uptime/boot time y top 3 por CPU y memoria.

CPU global = delta de la línea 'cpu' de /proc/stat entre dos lecturas. También
llevamos jiffies previos por proceso para el top-3 por CPU.
"""
import time

import procfs


def crear_recolector(verbose):
    prev_cpu = [None]      # línea cpu previa de /proc/stat
    prev_proc = {}         # {pid: jiffies}
    prev_t = [None]

    def recolectar(pids):
        ahora = time.time()
        dt = (ahora - prev_t[0]) if prev_t[0] else None

        # --- CPU global (delta) ---
        cpu_ahora = procfs.leer_cpu_global()
        cpu_pct = {}
        if prev_cpu[0]:
            deltas = [a - b for a, b in zip(cpu_ahora, prev_cpu[0])]
            total = sum(deltas) or 1
            cpu_pct = {
                "user": round(deltas[0] / total * 100, 1),
                "system": round(deltas[2] / total * 100, 1),
                "idle": round(deltas[3] / total * 100, 1),
                "iowait": round(deltas[4] / total * 100, 1) if len(deltas) > 4 else 0.0,
            }
        prev_cpu[0] = cpu_ahora

        # --- recorrido de procesos: conteo por estado, threads, zombies, tops ---
        conteo = {}
        threads_total = 0
        zombies = 0
        nuevos = {}
        por_cpu = []
        por_mem = []
        for pid in pids:
            try:
                st = procfs.leer_stat(pid)
                status = procfs.leer_status(pid)
            except procfs.ERRORES_PROC:
                continue
            estado = st["estado"]
            conteo[estado] = conteo.get(estado, 0) + 1
            threads_total += st["num_threads"]
            if estado == "Z":
                zombies += 1

            jiffies = st["utime"] + st["stime"]
            nuevos[pid] = jiffies
            if dt and pid in prev_proc:
                cpu = (jiffies - prev_proc[pid]) / procfs.CLK_TCK / dt * 100
                por_cpu.append((round(cpu, 1), pid, st["comm"]))
            rss = procfs._kb(status, "VmRSS")
            if rss:
                por_mem.append((rss, pid, st["comm"]))

        prev_proc.clear()
        prev_proc.update(nuevos)
        prev_t[0] = ahora

        por_cpu.sort(reverse=True)
        por_mem.sort(reverse=True)

        mem = procfs.leer_meminfo()
        btime = procfs.leer_btime()
        return {
            "cpu": cpu_pct,
            "load": procfs.leer_loadavg(),
            "memoria": {
                "MemTotal": mem.get("MemTotal"),
                "MemFree": mem.get("MemFree"),
                "Buffers": mem.get("Buffers"),
                "Cached": mem.get("Cached"),
                "SwapTotal": mem.get("SwapTotal"),
                "SwapFree": mem.get("SwapFree"),
            },
            "conteo_estados": conteo,
            "procesos_total": sum(conteo.values()),
            "threads_total": threads_total,
            "zombies": zombies,
            "uptime": round(procfs.leer_uptime(), 1),
            "boot_time": btime,
            "top_cpu": por_cpu[:3],
            "top_mem": por_mem[:3],
        }

    return recolectar
