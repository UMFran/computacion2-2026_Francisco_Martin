import socketserver

class MyTCPHandler(socketserver.BaseRequestHandler):

    def handle(self):
        datos = self.request.recv(4096)
        self.request.sendall(datos.upper())

if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 9999

    # Create the server, binding to localhost on port 9999
    with socketserver.TCPServer((HOST, PORT), MyTCPHandler) as server:
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.allow_reuse_address = True
        server.serve_forever()