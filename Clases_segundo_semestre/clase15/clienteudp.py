import socket

def pedir_con_reintentos(sock, mensaje, destino, intentos=3, timeout=20.0):
    """Manda un mensaje y espera respuesta, reintentando si se pierde."""
    sock.settimeout(timeout)
    for intento in range(1, intentos + 1):
        sock.sendto(mensaje, destino)
        try:
            respuesta, _ = sock.recvfrom(65535)
            return respuesta
        except TimeoutError:
            print(f'Intento {intento}: sin respuesta, reintento')
    return None

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    #s.settimeout(2.0)
    s.sendto(b'Hola', ('localhost', 8080))
    #respuesta, origen = s.recvfrom(4096)
    #print(f'Respuesta: {respuesta.decode()} desde {origen}')
    respuesta = pedir_con_reintentos(s, b'Hola', ('localhost', 8080))
    if respuesta is not None:
        print(f'Respuesta: {respuesta.decode()}')
    else:
        print('No se recibió respuesta después de varios intentos.')
