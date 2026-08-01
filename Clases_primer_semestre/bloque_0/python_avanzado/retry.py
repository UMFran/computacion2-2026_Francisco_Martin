import time
import random
import functools


def retry(max_attempts=3, delay=1, exceptions=Exception):
    """
    Decorador que reintenta una función si lanza una excepción.

    max_attempts : cuántas veces intentar en total
    delay        : segundos a esperar entre intentos
    exceptions   : qué excepciones capturar (una clase o tupla de clases)
    """
    def decorador(func):
        @functools.wraps(func)   # preserva el nombre y docstring de la función original
        def wrapper(*args, **kwargs):
            for intento in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)   # si funciona, devuelve el resultado

                except exceptions as e:
                    if intento < max_attempts:
                        print(f"Intento {intento}/{max_attempts} falló: {e}. Esperando {delay}s...")
                        time.sleep(delay)
                    else:
                        print(f"Intento {intento}/{max_attempts} falló: {e}.")
                        raise   # relanza la última excepción

        return wrapper
    return decorador


# ── Pruebas ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("=== Caso 1: falla los primeros intentos, luego tiene éxito ===\n")

    intentos = 0

    @retry(max_attempts=4, delay=0)   # delay=0 para que las pruebas sean rápidas
    def funcion_inestable():
        global intentos
        intentos += 1
        if intentos < 3:              # falla las primeras 2 veces, luego funciona
            raise ConnectionError("Servidor no disponible")
        return "Conectado exitosamente"

    resultado = funcion_inestable()
    print(f"Resultado: {resultado}\n")


    print("=== Caso 2: falla todos los intentos ===\n")

    @retry(max_attempts=3, delay=0)
    def siempre_falla():
        raise ConnectionError("Servidor caído")

    try:
        siempre_falla()
    except ConnectionError:
        print("Falló después de 3 intentos\n")


    print("=== Caso 3: solo captura excepciones específicas ===\n")

    @retry(max_attempts=3, delay=0, exceptions=(ValueError,))
    def falla_con_tipo_equivocado():
        raise ConnectionError("Este error NO debería ser capturado por retry")

    try:
        falla_con_tipo_equivocado()
    except ConnectionError as e:
        print(f"La excepción se propagó sin reintentos: {e}\n")


    print("=== Caso 4: uso real con probabilidad aleatoria ===\n")

    @retry(max_attempts=5, delay=0)
    def conectar_servidor():
        if random.random() < 0.7:     # 70% de chance de fallar
            raise ConnectionError("Servidor no disponible")
        return "Conectado exitosamente"

    try:
        resultado = conectar_servidor()
        print(f"Resultado final: {resultado}")
    except ConnectionError:
        print("Falló después de todos los intentos")