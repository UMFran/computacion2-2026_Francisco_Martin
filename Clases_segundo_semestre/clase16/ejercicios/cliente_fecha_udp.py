import socket
import sys

HOST, PORT = "localhost", 9999
data = " ".join(sys.argv[1:]) or "get"

# SOCK_DGRAM is the socket type to use for UDP sockets
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# As you can see, there is no connect() call; UDP has no connections.
# Instead, data is directly sent to the recipient via sendto().
sock.sendto(bytes(data + "\n", "utf-8"), (HOST, PORT))

try:
    received = str(sock.recv(1024), "utf-8")
    print("Sent:    ", data)
    print("Received:", received)
except TimeoutError:
    print("Sent:    ", data)
    print("Sin respuesta: se perdio el datagrama o el servidor no esta")
finally:
    sock.close()
