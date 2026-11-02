#!/usr/bin/env python3
"""Demostracion guiada del sistema, para la correccion.

Corre los seis momentos de la demo en orden, narrando que hay que mirar en
cada uno. Esta en Python y no en un script de shell a proposito: anda igual
en Windows, Linux y adentro del contenedor, y no sufre el manejo de
comillas de PowerShell ni el alias de curl.

Uso (con el servidor levantado, desde TP2/):
    python demo.py              todos los pasos
    python demo.py 3            solo el paso 3
    python demo.py 3 5          los pasos 3 y 5
    python demo.py --pausa      frena entre pasos (para ir explicando)

Si el servidor no esta levantado:
    docker compose up -d
"""
import sys
import time

import httpx

BASE = 'http://localhost:8000'
PAUSA = False


# ------------------------------------------------------------ presentacion

def titulo(n, texto):
    print()
    print('=' * 72)
    print(f'  PASO {n}  -  {texto}')
    print('=' * 72)


def decir(texto):
    """Lo que conviene explicar mientras se ve la salida."""
    print()
    for linea in texto.strip().split('\n'):
        print('  >> ' + linea.strip())


def frenar():
    if PAUSA:
        input('\n  [Enter para seguir]')


def encolar(c, tipo, timeout=300, **parametros):
    return c.post('/tareas', json={'tipo': tipo, 'parametros': parametros,
                                   'timeout': timeout}).json()['id']


def esperar_libre(c, limite=120):
    """Espera a que no quede nada en vuelo.

    Varios pasos narran lo que pasa suponiendo que los dos workers estan
    libres. Si se corre un subconjunto de pasos (`python demo.py 1 2 5`),
    las tareas del paso anterior pueden estar todavia ocupando los workers
    y el paso siguiente mostraria algo distinto de lo que narra.
    """
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite:
        e = c.get('/estadisticas').json()
        if e['workers']['ocupados'] == 0 and e['cola']['encoladas'] == 0:
            return
        time.sleep(0.5)


def final(c, tid, limite=300):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < limite:
        f = c.get(f'/tareas/{tid}').json()
        if f['estado'] in ('completada', 'fallida', 'cancelada'):
            return f
        time.sleep(0.1)
    return c.get(f'/tareas/{tid}').json()


# ----------------------------------------------------------------- pasos

def paso1(c):
    titulo(1, 'El sistema en reposo')
    e = c.get('/estadisticas').json()
    print(f"\n  workers:  {e['workers']['ocupados']}/{e['workers']['total']} ocupados")
    print(f"  cola:     {e['cola']['encoladas']} encoladas (maxsize {e['cola']['maxsize']})")
    print(f"  tareas:   {e['total']} en el registro")
    decir('''
        Hay 2 workers arrancados y ninguno ocupado: son dos corrutinas
        suspendidas en `await cola.get()`. No consumen CPU. El event loop
        esta bloqueado en el selector del sistema operativo esperando que
        pase algo -- eso es la clase 17 abajo de todo.
    ''')


def paso2(c):
    titulo(2, 'El POST responde sin esperar a la tarea')
    t0 = time.perf_counter()
    ids = [encolar(c, 'esperar', segundos=6) for _ in range(5)]
    dt = time.perf_counter() - t0
    print(f'\n  5 tareas de 6 segundos encoladas en {dt:.3f}s')
    for tid in ids:
        print(f'    {tid}  pendiente')
    decir(f'''
        Cinco tareas de 6 segundos cada una, y los cinco POST volvieron en
        {dt:.3f} segundos. Si el endpoint tardara lo que tarda la tarea, el
        diseno estaria mal: la consigna lo dice explicitamente. El POST solo
        crea la ficha, hace put_nowait del id y devuelve 201.
    ''')
    return ids


def paso3(c, ids=None):
    titulo(3, 'Ver el sistema trabajando')
    if not ids:
        ids = [encolar(c, 'esperar', segundos=6) for _ in range(5)]
        time.sleep(0.2)
    print()
    print('  %5s  %-32s  %s' % ('t', 'estados', 'workers / cola'))
    t0 = time.perf_counter()
    while True:
        e = c.get('/estadisticas').json()
        pe = e['por_estado']
        print('  %4.0fs  pend=%d ejec=%d compl=%-18d  %d/%d ocupados, %d en cola' % (
            time.perf_counter() - t0, pe['pendiente'], pe['ejecutando'],
            pe['completada'], e['workers']['ocupados'],
            e['workers']['total'], e['cola']['encoladas']))
        if pe['pendiente'] == 0 and pe['ejecutando'] == 0:
            break
        time.sleep(2)
    decir('''
        Nunca hay mas de 2 ejecutando, porque hay 2 workers. Las otras
        esperan en la asyncio.Queue. El ultimo escalon tiene un solo worker
        ocupado: quedaba una sola tarea.
        Esto es la medicion 3: el techo no es la cantidad de tareas, es la
        cantidad de workers.
    ''')
    return ids


def paso4(c, ids=None):
    titulo(4, 'La linea de tiempo')
    if not ids:
        print('\n  (no hay tareas de los pasos anteriores; encolo 5 nuevas)')
        ids = [encolar(c, 'esperar', segundos=3) for _ in range(5)]
        for tid in ids:
            final(c, tid)

    fichas = [c.get(f'/tareas/{tid}').json() for tid in ids]
    cero = min(f['encolada'] for f in fichas)
    print()
    print('  %-10s %-11s %9s %8s %8s %12s %7s' % (
        'id', 'estado', 'encolada', 'arranco', 'termino', 'esperoEnCola', 'duro'))
    for f in fichas:
        arranco = f'{f["inicio"] - cero:7.2f}s' if f['inicio'] else '      -'
        termino = f'{f["fin"] - cero:7.2f}s' if f['fin'] else '      -'
        espero = f'{f["inicio"] - f["encolada"]:11.2f}s' if f['inicio'] else '          -'
        duro = f'{f["fin"] - f["inicio"]:6.2f}s' if f['inicio'] and f['fin'] else '     -'
        print('  %-10s %-11s %8.2fs %s %s %s %s' % (
            f['id'], f['estado'], f['encolada'] - cero, arranco, termino, espero, duro))
    decir('''
        Esta tabla sola prueba cuatro cosas. Las cinco se encolaron casi en
        el mismo instante: el POST no espera a nadie. Arrancaron de a dos,
        en tres tandas, porque hay dos workers. Cada una duro lo mismo sin
        importar la congestion: el tiempo de EJECUCION no se degrada. Y lo
        que crecio fue la ESPERA EN COLA.
        De estos tres campos salen los promedios de /estadisticas.
    ''')


def paso5(c):
    titulo(5, 'Cancelacion: los dos caminos del DELETE')
    esperar_libre(c)   # los dos caminos solo se distinguen con workers libres
    a = encolar(c, 'esperar', segundos=60)
    b = encolar(c, 'esperar', segundos=60)
    z = encolar(c, 'esperar', segundos=60)
    time.sleep(1)
    print()
    print(f"  a = {a}  {c.get(f'/tareas/{a}').json()['estado']}")
    print(f"  b = {b}  {c.get(f'/tareas/{b}').json()['estado']}")
    print(f"  z = {z}  {c.get(f'/tareas/{z}').json()['estado']}   <- quedo en la cola")

    # Primero la encolada: si se cancela antes una que esta ejecutando, se
    # libera un worker que agarra la de la cola al instante.
    print('\n  1) DELETE de la que esta EN COLA')
    print('    ', c.delete(f'/tareas/{z}').json())
    print('  2) DELETE de la que esta EJECUTANDO')
    print('    ', c.delete(f'/tareas/{a}').json())
    c.delete(f'/tareas/{b}')
    time.sleep(1)

    print('\n  Como quedaron las fichas:')
    for tid, etq in ((z, 'estaba en cola'), (a, 'estaba ejecutando')):
        f = c.get(f'/tareas/{tid}').json()
        dur = f"{f['fin'] - f['inicio']:.2f}s" if f['inicio'] else 'nunca arranco'
        print('    %-20s %-11s %-42s %s' % (etq, f['estado'], f['motivo'], dur))

    d = encolar(c, 'esperar', segundos=1)
    print(f"\n  El worker sigue vivo: una tarea nueva quedo "
          f"{final(c, d)['estado']}")
    decir('''
        Son dos caminos distintos. La que estaba en cola no tenia ningun
        Task que cancelar: solo se marco la ficha, y el worker la descarta
        cuando la saque -- por eso inicio quedo en null, nunca arranco.
        La que estaba ejecutando si tenia un Task guardado en el dict
        `ejecutando`, y se le hizo cancel(). cancel() no la mata: le pide al
        loop que le lance CancelledError en su proximo await, que aca era el
        asyncio.sleep.
        Y cancelar una tarea no mata al worker. Por eso cada tarea corre en
        un Task aparte: si el worker hiciera `await ejecutar_una(tid)`
        directo, el unico Task cancelable seria el del worker.
        Ojo con el orden: se cancela primero la encolada, porque si no, al
        cancelar la que ejecuta se libera un worker que agarra la de la cola
        al instante.
    ''')


def paso6(c):
    titulo(6, 'El event loop bloqueado')
    esperar_libre(c)   # la latencia del GET solo se lee limpia sin otra carga
    iteraciones = 12_000_000
    print(f'\n  Tarea: hashear {iteraciones:,} iteraciones de SHA-256')
    print()
    print('  %-24s %10s %12s' % ('', 'calculo', 'un GET /tareas'))
    medido = {}
    for sin_ex in (True, False):
        tid = encolar(c, 'hashear', texto='demo',
                      iteraciones=iteraciones, sin_executor=sin_ex)
        time.sleep(0.3)
        t0 = time.perf_counter()
        c.get('/tareas')
        lat = (time.perf_counter() - t0) * 1000
        f = final(c, tid)
        medido[sin_ex] = lat
        print('  %-24s %9.2fs %10.1f ms' % (
            'SIN run_in_executor' if sin_ex else 'CON run_in_executor',
            f['resultado']['segundos'], lat))
    decir(f'''
        Sin executor el GET tarda {medido[True]/1000:.1f} segundos: el event
        loop es UN SOLO HILO y la corrutina que calcula no tiene ningun
        await donde ceder el control. No es contencion de CPU, es que nunca
        lo devuelve. Con executor, {medido[False]:.0f} milisegundos.
        Y lo mas importante: el calculo tarda LO MISMO en los dos casos. El
        executor no acelera nada, solo evita que bloquee a los demas.
        Durante ese lapso tampoco se hubiera disparado ningun timeout ni
        avanzado ningun otro worker.
    ''')


def paso7(c):
    titulo(7, 'Apagado ordenado')
    print('\n  Este paso se hace a mano, porque necesita mandar la senal:')
    print('\n    docker compose stop')
    print('    docker compose logs --tail 20')
    print('    ls estados/')
    decir('''
        En el log tienen que aparecer, en orden: "dejo de aceptar tareas
        nuevas", "worker N se retira ordenadamente" y "estado volcado en
        estados/estado_<timestamp>.json".
        El SIGTERM lo atrapa uvicorn, que corre el apagado del lifespan. Se
        mete un centinela por worker: cada uno termina lo que tiene entre
        manos y recien ahi se retira, asi ninguna tarea queda a medias. Si
        se agota el limite de 10 segundos, corta por cancelacion.
        El stop_grace_period de 20s del compose existe porque Docker manda
        SIGKILL a los 10 segundos por omision, y el volcado no llegaria a
        escribirse.
    ''')


def main():
    global PAUSA
    args = [a for a in sys.argv[1:] if a != '--pausa']
    PAUSA = '--pausa' in sys.argv
    pedidos = [int(a) for a in args if a.isdigit()] or [1, 2, 3, 4, 5, 6, 7]

    try:
        with httpx.Client(base_url=BASE, timeout=300) as c:
            c.get('/estadisticas')
            ids = None
            if 1 in pedidos:
                paso1(c); frenar()
            if 2 in pedidos:
                ids = paso2(c); frenar()
            if 3 in pedidos:
                ids = paso3(c, ids); frenar()
            if 4 in pedidos:
                paso4(c, ids); frenar()
            if 5 in pedidos:
                paso5(c); frenar()
            if 6 in pedidos:
                paso6(c); frenar()
            if 7 in pedidos:
                paso7(c)
            print()
    except httpx.HTTPError:
        print(f'\n  No hay nadie escuchando en {BASE}.')
        print('  Levantalo con:   docker compose up -d')
        print('  o sin Docker:    python -m uvicorn app.main:app --port 8000')
        sys.exit(1)


if __name__ == '__main__':
    main()
