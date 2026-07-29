"""Analizador File Descriptors: lista de FDs y su destino/tipo.

verbose controla cuántos FDs se detallan por proceso (en modo normal acotamos
para no llenar la pantalla; SIGUSR2 lo activa).
"""
import procfs


def crear_recolector(verbose):
    def recolectar():
        limite = None if verbose.value else 10
        procesos = []
        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                info = procfs.leer_fds(pid, limite=limite)
            except PermissionError:
                # FDs de un proceso de otro usuario: lo mostramos como inaccesible
                # (va PRIMERO para que no lo tape el except genérico de abajo).
                procesos.append({"pid": pid, "comm": st["comm"], "error": "permiso denegado"})
                continue
            except procfs.ERRORES_PROC:
                continue
            procesos.append({
                "pid": pid,
                "comm": st["comm"],
                "total": info["total"],
                "por_tipo": info["por_tipo"],
                "lista": info["lista"],
            })
        procesos.sort(key=lambda p: p.get("total", 0), reverse=True)
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
