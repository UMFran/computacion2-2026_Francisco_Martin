from multiprocessing import Process, Pipe

def hijo(conn):
    for i in range(5):
        msg = conn.recv()                        # espera el ping del padre
        print(f"[HIJO]  recibió: '{msg}' → responde pong-{i}")
        conn.send(f"pong-{i}")
    conn.close()

if __name__ == "__main__":
    conn_padre, conn_hijo = Pipe()               # duplex=True por defecto

    p = Process(target=hijo, args=(conn_hijo,))
    p.start()

    for i in range(5):
        msg = f"ping-{i}"
        conn_padre.send(msg)
        print(f"[PADRE] envió:   '{msg}'")
        respuesta = conn_padre.recv()            # espera el pong
        print(f"[PADRE] recibió: '{respuesta}'")

    p.join()
    conn_padre.close()
    print("Listo.")