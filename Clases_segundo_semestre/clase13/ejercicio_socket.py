import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(('localhost', 8080))
    s.sendall(b'Hola Mundo')
    respuesta = s.recv(4096)
    print(f'Recibido: {respuesta!r}') #se cierra el with junto con el socket
    