"""Analizador Señales (INFO de cada proceso, no las del monitor).

Lee las 5 máscaras hex de status y las decodifica a nombres legibles con
procfs.decodificar_mascara (que usa la tabla bit->nombre armada una sola vez).
"""
import procfs

# Qué línea de status corresponde a qué concepto.
MASCARAS = {
    "bloqueadas": "SigBlk",
    "ignoradas": "SigIgn",
    "capturadas": "SigCgt",     # con handler propio
    "pendientes": "SigPnd",     # pendientes al proceso
    "pendientes_grupo": "ShdPnd",
}


def crear_recolector(verbose):
    def recolectar():
        procesos = []
        for pid in procfs.listar_pids():
            try:
                st = procfs.leer_stat(pid)
                status = procfs.leer_status(pid)
            except (FileNotFoundError, ProcessLookupError, KeyError, IndexError, ValueError):
                continue
            decodificadas = {}
            for concepto, clave in MASCARAS.items():
                hexval = status.get(clave, "0")
                decodificadas[concepto] = procfs.decodificar_mascara(hexval)
            procesos.append({"pid": pid, "comm": st["comm"], **decodificadas})
        return {"procesos": procesos, "n": len(procesos)}

    return recolectar
