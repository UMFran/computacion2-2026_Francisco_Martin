"""Analizador Memoria: Vm* de status, page faults de stat, segmentos de maps."""
import procfs


def crear_recolector(verbose):
    def recolectar():
        procesos = []
        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                status = procfs.leer_status(pid)
                vm = procfs.leer_memoria_vm(status)
                # maps puede fallar por permisos en procesos de otro usuario.
                try:
                    segmentos = procfs.leer_maps(pid)
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    segmentos = None
                procesos.append({
                    "pid": pid,
                    "comm": st["comm"],
                    "vm": vm,
                    "minflt": st["minflt"],
                    "majflt": st["majflt"],
                    "segmentos": segmentos,
                })
            except procfs.ERRORES_PROC:
                continue
        # ordenamos por RSS descendente (los que no tienen RSS van al final)
        procesos.sort(key=lambda p: p["vm"].get("VmRSS") or 0, reverse=True)
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
