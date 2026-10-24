import socketserver
from datetime import datetime

class FechaUDPHandler(socketserver.BaseRequestHandler):
    """
    Responde la fecha y hora actual cuando el cliente manda "get".
    Igual que en el ejemplo, self.request es un par (datos, socket) y hay
    que contestar con sendto() porque en UDP no hay conexion.
    """

    def handle(self):
        data = self.request[0].strip()
        sock = self.request[1]
        print(f"{self.client_address[0]} wrote:")
        print(data)

        # El datagrama ya llego entero: no hace falta recv() ni framing.
        comando = data.decode("utf-8", errors="replace").lower()

        if comando == "get":
            respuesta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            respuesta = f"comando desconocido: {comando!r} (se espera 'get')"

        sock.sendto(respuesta.encode("utf-8"), self.client_address)

if __name__ == "__main__":
    HOST, PORT = "localhost", 9999
    with socketserver.UDPServer((HOST, PORT), FechaUDPHandler) as server:
        server.serve_forever()
