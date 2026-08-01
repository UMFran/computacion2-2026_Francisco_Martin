from multiprocessing import Process

def trabajo_hijo():
    print("Soy el hijo, voy a hacer trabajo específico de hijo")
    # Al terminar la función, el proceso hijo termina solo

if __name__ == "__main__":
    p = Process(target=trabajo_hijo)
    p.start()                          # equivale al fork()
    print(f"Soy el padre, mi hijo es {p.pid}")
    p.join()                           # equivale al os.wait()