#!/usr/bin/env python3
"""Ejercicio 4: Bytes y encoding.

Por que los sockets mandan bytes y no strings, y como se rompe UTF-8
cuando un recv() parte un caracter por la mitad.

    python3 ejercicio4.py
"""
import codecs
import socket
import struct
import sys
import threading
import time

# La consola de Windows usa cp1252 por defecto y no puede imprimir '€' ni
# emoji: sin esto, este mismo ejercicio muere con UnicodeEncodeError al
# escribir en pantalla. Es el mismo problema de fondo (texto vs bytes) pero
# del lado de la salida estandar en vez del socket.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = '127.0.0.1'
PUERTO = 8095


# --------------------------------------------------------------------
# 1. El TypeError
# --------------------------------------------------------------------

def punto1():
    print('=== 1. sendall() con un str ===')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.sendall('hola')                   # str, no bytes
        except TypeError as e:
            print(f'  TypeError: {e}')
    print('  Las formas correctas:')
    print(f"    b'hola'              -> {b'hola'!r}")
    print(f"    'hola'.encode()      -> {'hola'.encode()!r}")
    print()


# --------------------------------------------------------------------
# 2. Caracteres contra bytes
# --------------------------------------------------------------------

def punto2():
    print('=== 2. len(str) contra len(bytes) ===')
    print(f"  'ñ'.encode('utf-8')   -> {'ñ'.encode('utf-8')!r}")
    print(f"  'año'.encode('utf-8') -> {'año'.encode('utf-8')!r}")
    print(f"  len('año')            -> {len('año')} caracteres")
    print(f"  len('año'.encode())   -> {len('año'.encode('utf-8'))} bytes")
    print()
    print('  Cuantos bytes ocupa cada caracter en UTF-8:')
    for caracter in 'añ€𝄞':
        codificado = caracter.encode('utf-8')
        print(f"    {caracter!r:8} U+{ord(caracter):04X}  "
              f"{len(codificado)} byte(s)  {codificado!r}")
    print()


# --------------------------------------------------------------------
# 3. El bug del caracter partido
# --------------------------------------------------------------------

def punto3():
    print('=== 3. El caracter partido ===')
    datos = 'año'.encode('utf-8')               # b'a\xc3\xb1o', 4 bytes
    print(f'  completo: {datos!r} ({len(datos)} bytes)')
    primera_mitad = datos[:2]                   # corta la n con tilde al medio
    print(f'  mitad:    {primera_mitad!r}')
    try:
        print(primera_mitad.decode('utf-8'))
    except UnicodeDecodeError as e:
        print(f'  UnicodeDecodeError: {e}')
    print()

    print('  Lo mismo, pero simulado sobre un socket real:')
    demo_socket_partido()
    print()


def servidor_partidor(puerto, listo):
    """Manda 'ñ' partido en dos envios, con una pausa en el medio.

    Fuerza que el cliente vea el caracter cortado entre dos recv().
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, puerto))
        srv.listen(1)
        listo.set()
        conn, _dir = srv.accept()
        with conn:
            datos = 'mañana'.encode('utf-8')    # 7 bytes, 6 caracteres
            corte = 3                           # justo entre \xc3 y \xb1
            conn.sendall(datos[:corte])
            time.sleep(0.4)                     # que el recv() salga con 3 bytes
            conn.sendall(datos[corte:])


def demo_socket_partido():
    listo = threading.Event()
    threading.Thread(target=servidor_partidor, args=(PUERTO, listo),
                     daemon=True).start()
    listo.wait(timeout=5)
    with socket.create_connection((HOST, PUERTO), timeout=5) as s:
        pedazos = []
        while True:
            pedazo = s.recv(4096)
            if not pedazo:
                break
            pedazos.append(pedazo)
            print(f'    recv -> {pedazo!r}')
            # MAL: decodificar cada pedazo por separado
            try:
                print(f'      decode del pedazo: {pedazo.decode("utf-8")!r}')
            except UnicodeDecodeError as e:
                print(f'      decode del pedazo: UnicodeDecodeError: {e.reason}')
    # BIEN: juntar todo y recien ahi decodificar
    completo = b''.join(pedazos)
    print(f'    juntando todo: {completo!r} -> {completo.decode("utf-8")!r}')


# --------------------------------------------------------------------
# 4. Como se evita: framing + decodificar el mensaje completo
# --------------------------------------------------------------------

def punto4():
    print('=== 4. La solucion: framing, y decodificar recien al final ===')
    mensaje = 'mañana viajo a Japón 🇯🇵'
    payload = mensaje.encode('utf-8')
    print(f'  mensaje: {mensaje!r}')
    print(f'  {len(mensaje)} caracteres, {len(payload)} bytes')

    # Se manda con prefijo de longitud (ejercicio 3): la longitud va en BYTES,
    # nunca en caracteres, porque el receptor cuenta bytes.
    crudo = struct.pack('!I', len(payload)) + payload

    # Simulo una entrega en pedazos de 5 bytes, que parte caracteres al medio.
    buffer = b''
    for i in range(0, len(crudo), 5):
        buffer += crudo[i:i + 5]                # se ACUMULA, no se decodifica
    (longitud,) = struct.unpack('!I', buffer[:4])
    recuperado = buffer[4:4 + longitud].decode('utf-8')   # decode una sola vez
    print(f'  recuperado: {recuperado!r}')
    print(f'  {"OK: identico al original" if recuperado == mensaje else "ERROR"}')
    print()

    print('  Alternativa cuando hace falta decodificar en streaming:')
    decodificador = codecs.getincrementaldecoder('utf-8')()
    salida = ''
    for i in range(0, len(payload), 3):
        # El decodificador incremental se guarda los bytes sueltos que todavia
        # no forman un caracter completo, y los usa en la proxima llamada.
        salida += decodificador.decode(payload[i:i + 3])
    salida += decodificador.decode(b'', final=True)
    print(f'  codecs.getincrementaldecoder: {salida!r}')
    print(f'  {"OK" if salida == mensaje else "ERROR"}')
    print()


# --------------------------------------------------------------------
# 5. errors='replace'
# --------------------------------------------------------------------

def punto5():
    print("=== 5. errors='replace' ===")
    roto = 'año'.encode('utf-8')[:2]
    print(f'  {roto!r}.decode("utf-8", errors="replace") -> '
          f'{roto.decode("utf-8", errors="replace")!r}')
    print(f'  {roto!r}.decode("utf-8", errors="ignore")  -> '
          f'{roto.decode("utf-8", errors="ignore")!r}')
    print('  Ninguno de los dos arregla nada: uno pone un simbolo de relleno')
    print('  y el otro borra el byte. El dato original ya no se recupera.')
    print()


if __name__ == '__main__':
    punto1()
    punto2()
    punto3()
    punto4()
    punto5()


"""
Preguntas y respuestas
======================

1. Que error da `s.sendall('hola')` y por que?
       TypeError: a bytes-like object is required, not 'str'
   Porque un socket transporta bytes, no texto. Un str de Python 3 es una
   secuencia de caracteres Unicode (puntos de codigo), una estructura en memoria
   que no tiene una representacion unica en bytes: el mismo texto puede ocupar
   distinta cantidad de bytes segun se codifique en UTF-8, UTF-16, Latin-1...
   Python 3 se niega a elegir una codificacion por nosotros, justamente porque
   en Python 2 lo hacia y era una fuente enorme de bugs (el famoso
   UnicodeDecodeError que aparecia recien en produccion, con el primer nombre
   con acento). Hay que escribir `.encode('utf-8')` o usar un literal b'...'.
   Lo mismo al revés: recv() devuelve bytes, y para tratarlos como texto hay
   que llamar a .decode('utf-8').

2. Por que difieren len('año') y len('año'.encode('utf-8'))?
       len('año')                 -> 3     (tres caracteres: a, ñ, o)
       len('año'.encode('utf-8')) -> 4     (cuatro bytes: 61 c3 b1 6f)
   Porque UTF-8 es de ancho variable: codifica cada caracter en 1 a 4 bytes.
   Los ASCII (a-z, digitos, puntuacion) ocupan 1 byte, y por eso UTF-8 es
   compatible hacia atras con ASCII. La 'ñ' (U+00F1) necesita 2 bytes: c3 b1.
   El euro '€' (U+20AC) necesita 3, y los emoji o los simbolos musicales, 4.
   Consecuencia practica para sockets: la longitud en caracteres NO sirve para
   nada del lado de la red. Un prefijo de longitud tiene que contar BYTES, y
   `for c in texto` no se corresponde con `for b in texto.encode()`.

3. El bug del caracter partido:
       datos = 'año'.encode('utf-8')       # b'a\\xc3\\xb1o'
       datos[:2]                           # b'a\\xc3'  <- la n quedo a medias
       datos[:2].decode('utf-8')
       UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc3 in position 1:
       unexpected end of data
   El byte c3 anuncia "arranca un caracter de 2 bytes", pero el segundo nunca
   llega. El decodificador no puede inventarlo, asi que falla.
   Sobre un socket esto no es hipotetico: recv() corta donde se le da la gana,
   y nada garantiza que el corte caiga en el limite de un caracter. Con texto
   en castellano el bug aparece de a ratos y solo cuando hay acentos o enies,
   que es lo peor que le puede pasar a un bug: intermitente y dependiente de
   los datos. La salida del programa lo muestra con 'mañana' partido en 3+4.

4. Como se evita en un cliente real?
   Haciendo bien el framing (ejercicio 3) y decodificando el MENSAJE COMPLETO,
   nunca cada pedazo suelto. El orden correcto es:
       1) recv() hasta tener un mensaje entero segun el framing (delimitador o
          prefijo de longitud), acumulando en un buffer de bytes;
       2) recien ahi, .decode('utf-8') sobre esos bytes completos.
   Nunca al reves. Todo el manejo de red se hace en bytes; el texto aparece en
   el ultimo paso, cuando ya se sabe donde empieza y donde termina el mensaje.
   Detalle importante: el prefijo de longitud tiene que expresar bytes. Si uno
   pone len(texto) en vez de len(texto.encode()), el receptor lee de menos y
   todo el flujo se desincroniza, que es el problema del punto 6 del ejercicio 3.
   Con delimitador \\n hay una ventaja adicional: en UTF-8 los bytes de
   continuacion siempre tienen el bit alto en 1, asi que el byte 0x0A ('\\n')
   no puede aparecer nunca dentro de un caracter multibyte. Buscar el
   delimitador a nivel de bytes es seguro; con otras codificaciones (UTF-16)
   no lo seria.
   Cuando de verdad hace falta procesar texto a medida que llega (un chat en
   vivo, una respuesta larga), existe codecs.getincrementaldecoder('utf-8'),
   que se guarda los bytes incompletos entre llamadas. Es lo que usa por dentro
   socket.makefile('r', encoding='utf-8').

5. Cuando es aceptable errors='replace'?
   Solo cuando la salida es para que la mire una persona y perder informacion
   es preferible a que el programa se caiga:
   - logs y mensajes de depuracion (imprimir lo que llego sin morir en el
     intento);
   - un visor de datos ajenos que uno no controla, donde vale mas mostrar algo
     imperfecto que nada;
   - herramientas de inspeccion tipo hexdump o un sniffer.
   NO es aceptable para datos que se van a guardar, reenviar, comparar o
   procesar. El caracter de reemplazo (U+FFFD) es irreversible: destruye el
   byte original y convierte un error ruidoso, facil de diagnosticar, en
   corrupcion silenciosa que aparece tres capas mas abajo. Si el texto llega
   partido, el problema no es el decode: es el framing, y errors='replace' lo
   tapa en vez de arreglarlo.
   Como regla: 'strict' (el default) en el camino de los datos, 'replace' solo
   en el camino de los logs.
"""
