"""Analizador Scheduling: nice, priority, policy, RT prio, affinity, ctx switches,
utime/stime, SID/PGID."""
import procfs


def crear_recolector(verbose):
    def recolectar():
        procesos = []
        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                status = procfs.leer_status(pid)
            except (FileNotFoundError, ProcessLookupError, KeyError, IndexError, ValueError):
                continue
            procesos.append({
                "pid": pid,
                "comm": st["comm"],
                "nice": st["nice"],
                "priority": st["priority"],
                "policy": procfs.POLITICAS_SCHED.get(st["policy"], str(st["policy"])),
                "rt_priority": st["rt_priority"],
                "affinity": status.get("Cpus_allowed_list", "?"),
                "ctx_vol": int(status.get("voluntary_ctxt_switches", 0)),
                "ctx_inv": int(status.get("nonvoluntary_ctxt_switches", 0)),
                "utime": st["utime"],
                "stime": st["stime"],
                "sid": st["sid"],
                "pgid": st["pgid"],
            })
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
