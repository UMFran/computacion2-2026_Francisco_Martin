#!/usr/bin/env python3
"""Ejercicio 6: El limite del servidor secuencial (prepara la clase 14).

Un servidor que tarda 10s por cliente, y varios clientes a la vez. Mide
cuanto espera cada uno y muestra que la cola de listen() guarda, pero no
atiende.

    python3 ejercicio6.py                    # 4 clientes, listen(5), demora 3s
    python3 ejercicio6.py --clientes 4 --backlog 1
    python3 ejercicio6.py --demora 10
    python3 ejercicio6.py --servidor         # solo el servidor, para usar nc
    python3 ejercicio6.py --servidor --backlog 1

Para el punto 3 hace falta mirar el estado de las conexiones mientras el
servidor esta ocupado. En otra terminal:
    ss -tan sport = :8080 or dport = :8080      (Linux)
    netstat -an | findstr 8080                  (Windows)
"""
import socket
import subprocess
import sys
import threading
import time

HOST = '127.0.0.1'
PUERTO = 8080


def servidor(demora=3.0, backlog=5, atender_n=None):
    """Servidor SECUENCIAL: accept(), atender, y recien despues otro accept()."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PUERTO))
        srv.listen(backlog)             # <-- tamanio de la cola de pendientes
        print(f'[servidor] escuchando en {HOST}:{PUERTO}, '
              f'listen({backlog}), demora {demora}s por cliente')
        atendidos = 0
        while atender_n is None or atendidos < atender_n:
            conn, direccion = srv.accept()
            atendidos += 1
            t = time.perf_counter()
            print(f'[servidor] accept() #{atendidos} <- {direccion[1]} '
                  f'(t={t - T0:.1f}s)')
            try:
                with conn:
                    datos = conn.recv(4096)
                    if datos:
                        time.sleep(demora)       # simula trabajo pesado
                        conn.sendall(b'ECHO: ' + datos)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f'[servidor] {direccion[1]} corto: {type(e).__name__}')
            print(f'[servidor] listo con {direccion[1]} '
                  f'(t={time.perf_counter() - T0:.1f}s)')


def cliente(n, resultados):
    """Se conecta, manda, y mide cuanto tarda cada etapa."""
    t_inicio = time.perf_counter()
    try:
        s = socket.create_connection((HOST, PUERTO), timeout=120)
    except OSError as e:
        # Con backlog lleno, algunos sistemas rechazan la conexion aca.
        print(f'  cliente-{n}: connect() FALLO: {type(e).__name__}')
        resultados[n] = None
        return
    t_conectado = time.perf_counter()
    with s:
        s.sendall(f'soy el cliente {n}\n'.encode())
        respuesta = s.recv(4096)
    t_fin = time.perf_counter()
    print(f'  cliente-{n}: connect() a los {t_conectado - T0:.1f}s, '
          f'respuesta a los {t_fin - T0:.1f}s '
          f'(espero {t_fin - t_conectado:.1f}s despues de conectar)')
    resultados[n] = (t_conectado - t_inicio, t_fin - t_conectado)


def estado_conexiones():
    """Lista las conexiones al puerto 8080 segun el sistema operativo.

    Devuelve (lineas, establecidas_del_lado_servidor). El conteo importa:
    sobre loopback aparecen los DOS extremos de cada conexion, asi que hay
    que quedarse solo con las que tienen 8080 como direccion LOCAL.
    """
    try:
        if sys.platform == 'win32':
            comando, col_local = ['netstat', '-an'], 1
        else:
            comando, col_local = ['ss', '-tan'], 3
        salida = subprocess.run(comando, capture_output=True,
                                text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return None, 0

    lineas = [l for l in salida.splitlines() if f':{PUERTO}' in l]
    establecidas = 0
    for linea in lineas:
        partes = linea.split()
        if len(partes) <= col_local:
            continue
        local_es_8080 = partes[col_local].endswith(f':{PUERTO}')
        # netstat dice ESTABLISHED; ss dice ESTAB.
        if local_es_8080 and ('ESTAB' in linea.upper()):
            establecidas += 1
    return lineas, establecidas


def demo(clientes=4, demora=3.0, backlog=5):
    print(f'=== Servidor secuencial: {clientes} clientes, listen({backlog}), '
          f'{demora}s de trabajo por cliente ===\n')
    hilo_srv = threading.Thread(target=servidor,
                                args=(demora, backlog, clientes), daemon=True)
    hilo_srv.start()
    time.sleep(0.5)

    resultados = {}
    hilos = [threading.Thread(target=cliente, args=(i + 1, resultados))
             for i in range(clientes)]
    inicio = time.perf_counter()
    for h in hilos:
        h.start()
        time.sleep(0.15)            # arrancan casi juntos, en orden previsible

    # Punto 3 y 4: mirar el estado de las conexiones MIENTRAS el servidor
    # esta ocupado con el primero.
    time.sleep(1.0)
    lineas, estab = estado_conexiones()
    if lineas:
        print(f'\n  --- estado de las conexiones al puerto {PUERTO} '
              f'(el servidor sigue con el cliente 1) ---')
        for l in lineas:
            print(f'    {l.strip()}')
        print(f'  (sobre loopback aparecen los dos extremos de cada conexion:')
        print(f'   una linea con :{PUERTO} como origen y otra como destino)')
        print(f'  {estab} conexiones ESTABLECIDAS del lado del servidor, y el')
        print(f'  servidor llamo a accept() UNA sola vez.')
        print(f'  El handshake de las otras lo completo el KERNEL.\n')

    for h in hilos:
        h.join()
    total = time.perf_counter() - inicio

    print(f'\n=== Resumen ===')
    print(f'  {clientes} clientes en {total:.1f}s')
    print(f'  serial esperado: {clientes} x {demora}s = {clientes * demora:.1f}s')
    print(f'  si fuera concurrente: ~{demora:.1f}s')
    exitosos = [v for v in resultados.values() if v]
    if exitosos:
        peor = max(e[1] for e in exitosos)
        print(f'  el que peor la paso espero {peor:.1f}s DESPUES de que su')
        print(f'  connect() ya habia devuelto con exito')
    fallados = [k for k, v in resultados.items() if v is None]
    if fallados:
        print(f'  clientes cuyo connect() fallo: {fallados}')


T0 = time.perf_counter()

if __name__ == '__main__':
    args = sys.argv[1:]

    def opcion(nombre, default, tipo=int):
        return tipo(args[args.index(nombre) + 1]) if nombre in args else default

    backlog = opcion('--backlog', 5)
    demora = opcion('--demora', 3.0, float)
    clientes = opcion('--clientes', 4)

    try:
        if '--servidor' in args:
            servidor(demora, backlog)
        else:
            demo(clientes, demora, backlog)
    except KeyboardInterrupt:
        print('\nCortado')


"""
Preguntas y respuestas
======================

1. Dos clientes al mismo tiempo. Escribo en el segundo: responde?
   No. El servidor esta trabado dentro de atender() con el primer cliente y no
   vuelve a accept() hasta terminar. El segundo cliente puede escribir todo lo
   que quiera: sus bytes llegan a la maquina, el kernel los guarda en el buffer
   de recepcion de esa conexion, y ahi se quedan. Nadie los lee, porque el
   proceso servidor ni siquiera sabe que esa conexion existe.
   Lo desconcertante es que del lado del cliente TODO parece normal: el
   connect() funciono, el sendall() funciono, no hay ningun error. Solo que la
   respuesta no llega.

2. Cuanto tarda el segundo cliente en ser atendido?
   Lo que le falte al primero, mas su propio tiempo de trabajo. Con demora de
   3s: el primero responde a los ~3s y el segundo a los ~6s. El N-esimo cliente
   espera (N-1) x demora antes de que lo empiecen a atender.
   Con la demora de 10s del enunciado, el segundo espera 10s y el cuarto, 30s.
   Corriendo `python3 ejercicio6.py --clientes 4 --demora 3` se ve en el
   resumen: 4 clientes tardan ~12s (4 x 3), no ~3s.

3. Quien completo el handshake del segundo cliente, si el servidor nunca llamo
   a accept() para el?
   El KERNEL, sin intervencion del programa. Y esta es la idea central del
   ejercicio.
   Cuando se llama a listen(), el socket pasa a ser pasivo y el kernel se hace
   cargo del handshake por su cuenta. Mantiene DOS colas:
     - la cola SYN (conexiones a medio handshake, que recibieron el SYN y
       contestaron SYN-ACK, esperando el ACK final);
     - la cola de ACCEPT (conexiones con el handshake YA COMPLETO, esperando a
       que la aplicacion las retire).
   accept() no participa del handshake: lo unico que hace es sacar una conexion
   ya terminada de la segunda cola y devolverla como socket nuevo. Si la cola
   esta vacia, bloquea.
   Por eso `ss` muestra ESTAB: para TCP la conexion existe y esta establecida.
   El servidor de aplicacion no se entero todavia, pero eso a TCP no le importa.
   En la salida de este programa se ve directo: varias lineas ESTABLISHED
   cuando el servidor imprimio un solo accept().

4. Que representa Recv-Q en la linea LISTEN?
   En una linea LISTEN, ss reinterpreta las columnas: NO son bytes.
     Recv-Q = cantidad de conexiones en la cola de accept() esperando ser
              retiradas por la aplicacion.
     Send-Q = el maximo de esa cola, o sea el backlog efectivo de listen().
   Asi que una linea `LISTEN 3 5` significa "3 conexiones esperando, capacidad
   para 5". Al conectar un tercer cliente, Recv-Q sube a 3.
   Es la metrica que hay que mirar en produccion: un Recv-Q que se mantiene
   alto significa que la aplicacion no da abasto para hacer accept(), y las
   conexiones se estan acumulando aunque el servidor "no de error".
   (En Windows netstat no muestra estas columnas; el equivalente se ve con
   ss en Linux o con la salida de este programa.)

5. Con listen(1) y cuatro clientes, que pasa con el cuarto?
   Depende del sistema, y las dos variantes valen la pena:
   - Linux: por defecto (tcp_abort_on_overflow=0) el kernel DESCARTA el SYN en
     silencio. El cliente no recibe nada, reintenta el SYN varias veces con
     espera creciente, y suele terminar entrando cuando se libera lugar. Si no,
     falla con TimeoutError bastante despues. Lo notable es que no hay error
     inmediato: solo lentitud inexplicable.
   - Windows: tiende a rechazar con RST, y el cliente ve ConnectionRefusedError.
   Ademas Linux redondea el backlog hacia arriba y lo acota con
   /proc/sys/net/core/somaxconn, asi que listen(1) puede permitir mas de una
   conexion en cola. Por eso la salida de este programa reporta lo que pasa de
   verdad en la maquina donde se corre, en vez de dar por sentado un resultado.
   El punto conceptual, ese si es universal: el backlog es finito, y cuando se
   llena las conexiones nuevas se pierden o se rechazan.

6. Por que es falso que "el cliente conecto, asi que el servidor lo esta
   atendiendo"?
   Porque son dos eventos distintos, separados por una cola y por una cantidad
   de tiempo arbitraria:
     handshake completo  ->  lo hace el kernel, sin preguntarle a nadie
     accept()            ->  lo hace la aplicacion, cuando puede
   Entre uno y otro puede pasar un milisegundo o diez minutos, segun cuan
   ocupada este la aplicacion. Un connect() exitoso prueba UNICAMENTE que hay
   una maquina viva con un socket en LISTEN sobre ese puerto. No prueba que el
   proceso servidor este sano, ni que este leyendo, ni que exista siquiera como
   proceso funcional (podria estar en deadlock, o trabado en un sleep, y el
   kernel seguiria aceptando conexiones en su nombre).
   Consecuencias practicas:
   - Un health check que solo abre una conexion TCP da verde sobre un servidor
     completamente colgado. Por eso los checks serios mandan una peticion real
     y esperan una respuesta valida.
   - Al diagnosticar, ver ESTAB en ss no significa que la aplicacion este
     trabajando: hay que mirar Recv-Q en la linea LISTEN.
   - Del lado del cliente, el timeout no es opcional (ejercicio 5): es lo unico
     que distingue "me estan por atender" de "no me van a atender nunca".

7. Tres formas de resolverlo (todas del bloque de concurrencia):
   a) UN HILO POR CLIENTE (clase 10). Despues de accept(), se lanza un
      threading.Thread con la conexion y el bucle vuelve a accept() de
      inmediato. Es lo que ya hace el echo_server.py de la clase.
      A favor: simple, memoria compartida, poco codigo. En contra: cada hilo
      cuesta ~8 MB de stack, y el GIL limita el trabajo CPU-bound (aunque para
      I/O no molesta, porque se libera durante recv/send). Se rompe en el orden
      de los miles de clientes.
   b) UN PROCESO POR CLIENTE, con fork() o multiprocessing (clase 4). Es el
      modelo clasico de Apache prefork y del inetd de Unix.
      A favor: aislamiento real (si un cliente hace crashear a su proceso, los
      demas ni se enteran) y sin GIL. En contra: mucho mas caro que un hilo y
      la comunicacion entre procesos requiere IPC explicito.
   c) UN POOL de workers, de hilos o de procesos (clase 9). Se crean N workers
      al arrancar y se reparten las conexiones por una cola.
      A favor: acota el consumo de recursos (no hay explosion de hilos con
      10.000 clientes) y evita el costo de crear y destruir todo el tiempo.
      En contra: mas de N clientes lentos simultaneos vuelven a hacer cola, o
      sea que el problema se mitiga pero no desaparece.
   Y las dos que vienen despues, que son las que usan los servidores reales:
   d) MULTIPLEXAR con select()/poll()/epoll (clase 17): un solo hilo que vigila
      muchos sockets a la vez y atiende al que tenga datos listos.
   e) ASYNCIO (clase 19): lo mismo, pero con corrutinas en vez de callbacks.
   La eleccion de fondo es siempre la misma: no hay que dejar de llamar a
   accept(). Todas estas tecnicas son formas distintas de sacar el trabajo lento
   fuera del camino del bucle de accept().
"""
