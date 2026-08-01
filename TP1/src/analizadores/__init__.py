"""Paquete de analizadores del monitor.

Un módulo por dimensión (resumen, memoria, fds, threads, senales, scheduling,
sistema). Cada uno expone `crear_recolector(verbose)` que devuelve la función
encargada de leer /proc para esa dimensión. El loop común está en base.py.
"""
