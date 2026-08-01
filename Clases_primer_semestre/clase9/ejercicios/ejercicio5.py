#!/usr/bin/env python3
"""
Procesador de imágenes paralelo.
Simula procesamiento de imágenes usando matrices.
"""
from multiprocessing import Pool
import time
import random

def crear_imagen(size):
    """Crea una 'imagen' como lista de listas."""
    return [[random.randint(0, 255) for _ in range(size)]
            for _ in range(size)]

def aplicar_filtro(imagen):
    """Aplica un filtro blur 3x3 (CPU-intensive)."""
    size = len(imagen)
    resultado = [[0] * size for _ in range(size)]

    for i in range(1, size - 1):
        for j in range(1, size - 1):
            suma = 0
            for di in [-1, 0, 1]:
                for dj in [-1, 0, 1]:
                    suma += imagen[i + di][j + dj]
            resultado[i][j] = suma // 9

    return resultado

def procesar_imagen(args):
    """Procesa una imagen y devuelve métricas."""
    idx, imagen = args
    inicio = time.time()
    resultado = aplicar_filtro(imagen)
    duracion = time.time() - inicio
    return idx, duracion, sum(sum(row) for row in resultado)

if __name__ == "__main__":
    NUM_IMAGENES = 8
    SIZE = 100

    print(f"Creando {NUM_IMAGENES} imágenes de {SIZE}x{SIZE}...")
    imagenes = [(i, crear_imagen(SIZE)) for i in range(NUM_IMAGENES)]

    # Procesar secuencialmente
    print("\nProcesamiento secuencial:")
    inicio = time.time()
    for img in imagenes:
        procesar_imagen(img)
    tiempo_secuencial = time.time() - inicio
    print(f"Tiempo: {tiempo_secuencial:.2f}s")

    # Procesar en paralelo
    print("\nProcesamiento paralelo (4 workers):")
    inicio = time.time()
    with Pool(4) as pool:
        resultados = pool.map(procesar_imagen, imagenes)
    tiempo_paralelo = time.time() - inicio

    for idx, duracion, checksum in resultados:
        print(f"  Imagen {idx}: {duracion:.3f}s")

    print(f"Tiempo total: {tiempo_paralelo:.2f}s")
    print(f"Speedup: {tiempo_secuencial / tiempo_paralelo:.2f}x")