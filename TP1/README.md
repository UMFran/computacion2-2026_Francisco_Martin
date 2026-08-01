# Monitor de Procesos y Threads

**Computación II — Universidad de Mendoza — 2026**
Trabajo Práctico Nº 1 · Autor: Francisco Martín

Hice un monitor del sistema en tiempo real (estilo `htop`) que muestra la **anatomía
interna** de cada proceso y sus threads leyendo `/proc` directamente (sin `psutil`). Lo
armé como un **sistema multiproceso**: tengo analizadores especializados corriendo en
paralelo, que escriben un snapshot compartido en memoria, y una TUI que lo renderiza en 7
vistas alternables.

---

## 1. Descripción general

Para cada proceso extraigo siete dimensiones de información (resumen, memoria, file
descriptors, threads, señales, scheduling y estado global del sistema). Cada dimensión la
produce un **proceso analizador independiente** con su propio intervalo de refresco. Todos
publican en un **`multiprocessing.Manager().dict()`** que uso como snapshot global, y el
proceso de display lee ese snapshot y lo muestra con [`rich`](https://rich.readthedocs.io/)
en una interfaz de texto que se navega por teclado.

## 2. Cómo correr

Requisito: Docker + Docker Compose. Todo corre dentro de un contenedor Linux.

```bash
docker compose up --build
```

> **Importante para interactuar con el teclado (navegación, filtros, cambio de vista):**
> `docker compose up` muestra la TUI pero **no reenvía las teclas** al contenedor.
> Para usar la interfaz de forma interactiva, corré:
>
> ```bash
> docker compose run --rm monitor
> ```
>
> Esto adjunta el teclado (stdin + TTY) al contenedor. Con `up` la vista se ve y se
> actualiza sola, pero las teclas solo responden con `run`.

Para salir: `q` (o `Ctrl+C`).

### Controles

| Tecla | Acción |
|-------|--------|
| `1`–`7` o `r/m/f/t/s/p/g` | Cambiar de vista |
| `↑` `↓` | Navegar la lista de procesos |
| `Enter` | Pin del proceso seleccionado (queda fijo aunque cambie el orden) |
| `/` | Filtrar por comando |
| `u` | Filtrar por usuario |
| `c` | Ciclar ordenamiento (CPU% → RSS → PID) |
| `+` / `-` | Ajustar el intervalo de refresco de la vista activa |
| `h` / `?` | Ayuda |
| `q` | Salir limpio |

### Señales que responde el monitor

Con el monitor corriendo (PID 1 dentro del contenedor), desde otra terminal:

```bash
docker compose exec monitor sh
kill -USR1 1   # dump del snapshot a dump_<timestamp>.json
kill -USR2 1   # toggle modo verbose
kill -HUP  1   # releer config.json (intervalos) en caliente
kill -TERM 1   # shutdown limpio (igual que SIGINT / Ctrl+C)
```

## 3. Arquitectura

```
                    ┌──────────────────────────────────────────────┐
                    │        SNAPSHOT GLOBAL  (Manager.dict)         │
                    │   lo posee el proceso servidor del Manager     │
                    │   "resumen":{datos,ts}  "memoria":{datos,ts}   │
                    │   "fds" ... "threads" ... "senales" ...        │
                    │   "scheduling" ...      "sistema":{datos,ts}   │
                    └── ▲ ▲ ▲ ▲ ▲ ▲ ▲ ───────────────────┬──────────┘
      escriben SU clave  │ │ │ │ │ │ │                    │ lee (polling)
   (with lock solo p/dump)│ │ │ │ │ │                    │
        ┌────────┬────────┼─┼─┼─┼─┼─┼────────┐           │
   ┌────▼───┐┌───▼───┐┌───▼┐┌▼──┐┌▼───┐┌─────▼┐┌───────┐ │  ┌──────────────┐
   │Resumen ││Memoria││FDs ││Thr││Señ ││Sched ││Sistema│ │  │  DISPLAY TUI │
   │  2s    ││  3s   ││ 5s ││2s ││10s ││ 10s  ││  2s   │ │  │  (rich)      │
   └───┬────┘└───┬───┘└─┬──┘└┬──┘└┬───┘└──┬───┘└───┬───┘ │  │  + thread de │
       └─────────┴──────┴────┴────┴───────┴────────┘     │  │    teclado   │
                    cada analizador lee /proc            │  └──────┬───────┘
                    por su cuenta (Value = su intervalo)  │        │ +/- escribe
                              │                            │        ▼ al Value
                              ▼                    lee ─────┘   del intervalo
                       /proc  (kernel)
       ────────────────────────────────────────────────────────────────
       Proceso principal = DISPLAY + MANEJADOR DE SEÑALES.
       Señales INT/TERM/HUP/USR1/USR2 → el handler solo prende un flag;
       el loop de la TUI lee el flag y ejecuta la acción real.
```

### Componentes

| Componente | Cómo lo resolví | Archivo |
|------------|-----------------|---------|
| **Recolección de PIDs** | Cada analizador llama `procfs.listar_pids()` y lee las carpetas de `/proc`. No hice un proceso "recolector" central que reparta trabajo (ver *Decisiones de diseño*). | [`procfs.py`](src/procfs.py) |
| **7 analizadores** | Un proceso independiente por dimensión, todos corriendo un loop genérico común. | [`analizadores/`](src/analizadores/) |
| **Agregador** | Lo cumple el **proceso servidor del `Manager`**: es el único que posee el dict y serializa todas las escrituras. No armé un proceso agregador aparte. | (Manager) |
| **Display (TUI)** | Renderiza la vista activa leyendo el snapshot; lee el teclado en un thread. | [`display.py`](src/display.py) |
| **Manejador de señales** | Handlers async-signal-safe que solo prenden flags. | [`senales.py`](src/senales.py) |

## 4. Decisiones de diseño

### 4.1 IPC que elegí para cada comunicación

| Comunicación | Mecanismo | Por qué lo elegí |
|--------------|-----------|------------------|
| Analizadores → snapshot global | **`Manager().dict()`** | Es una estructura anidada, con muchos escritores (7) y un lector; el proxy del Manager serializa el acceso a través de su proceso servidor y soporta valores complejos (dicts, listas). |
| Display → analizador (cambiar intervalo) | **`Value('d')`** por analizador | Es un escalar de alta frecuencia; `Value` es memoria compartida cruda (mmap), sin pasar por el servidor del Manager ni picklear nada. Un `Manager.dict` acá sería carísimo para un solo float. |
| Toggle verbose (SIGUSR2) → analizadores | **`Value('i')`** compartido | Igual que arriba: un flag entero simple, de lectura frecuente. |
| Coordinación de escritura para el dump | **`Lock`** | Ver *race conditions*. |

**¿Por qué no usé `Queue`/`Pipe`?** El patrón de datos acá es *"cada productor mantiene el
último valor de su clave y el consumidor lo mira cuando quiere"* (estado más reciente),
no un flujo productor-consumidor donde cada mensaje importa. Para "último estado" un dict
compartido me encaja mejor que una cola: no se acumulan mensajes viejos, el lector siempre
ve el valor actual y no tengo que drenar nada. Habría elegido `Queue`/`Pipe` si necesitara,
por ejemplo, un histórico de eventos sin perder ninguno.

### 4.2 `Manager` vs `Value`/`Array`

- Usé **`Manager.dict`** para el snapshot: guarda estructuras que crecen y anidan (por
  proceso, por thread, listas de FDs…). Vive en un proceso servidor separado; cada operación
  es una llamada serializada (más cara, pero flexible y segura entre procesos).
- Usé **`Value`** para los intervalos y el flag verbose: son escalares de tipo simple (`d`,
  `i`). Van en memoria compartida mapeada, con un lock interno propio; lectura/escritura
  baratísima.
- **`Array`** no lo usé: no tengo un vector de escalares de tamaño fijo que justifique
  compartir por mmap; todo lo "estructurado" ya lo tengo en el `Manager.dict`.

### 4.3 Race conditions

- **Escrituras concurrentes al snapshot**: cada analizador escribe **solo su propia clave**
  con `snapshot[nombre] = {...}` (reasignación completa, no mutación in-place — un
  `snapshot[k]["x"]=…` no se propaga en un proxy de Manager). Ese `__setitem__` es **atómico**
  porque viaja como un pedido único al servidor del Manager, que los serializa. Como no hay
  dos analizadores tocando la misma clave, decidí que **no hace falta lock entre ellos**.
- **Lectura coherente para el dump (SIGUSR1)**: acá sí necesito coordinar. En `volcar_dump`
  ([main.py](src/main.py)) tomo un **`Lock`** compartido para copiar las 7 claves de una;
  como todos los analizadores escriben bajo ese mismo lock, mientras dura la copia nadie
  escribe → el `dump_*.json` me queda como una foto coherente y no una mezcla de instantes
  distintos. La copia (rápida) la hago dentro del lock; el volcado a disco (lento) lo dejo
  afuera, para no frenar a los 7 analizadores durante el I/O.
- **El display NO toma el lock**: lee de a una clave (que ya es atómica) a ~10 fps; decidí
  que la contención no vale la pena y una vista con claves de instantes levemente distintos
  es irrelevante visualmente.

### 4.4 Intervalos por defecto

Los tomé de la tabla de la consigna y siguen la **volatilidad del dato**:

| Vista | Default | Por qué |
|-------|---------|---------|
| Resumen, Threads, Sistema | 2 s | CPU%/estado cambian rápido; lo quiero ver fluido. |
| Memoria | 3 s | Cambia, pero más lento que la CPU. |
| FDs | 5 s | Los FDs no varían tanto entre refrescos. |
| Señales, Scheduling | 10 s | Máscaras de señales, nice y policy casi nunca cambian. |

Los dejé ajustables en caliente con `+`/`-`, con mínimos por vista (`display.MIN_INT`).

### 4.5 `fork` vs `spawn`/`forkserver`

Fijé **`fork`** explícitamente ([main.py](src/main.py)). En Linux es el default y me permite
que los hijos **hereden** el `Manager.dict`, los `Value`, el `Lock` y hasta los *closures*
(`crear_recolector(...)`) sin picklear ni reimportar. Con `spawn`, pasar un closure como
argumento del `Process` me fallaría (no es picklable) y tendría que reestructurar todo.
`fork` además es más barato al arrancar. La contra clásica de `fork` (heredar estado de
threads) no me afecta: forkeo **antes** de crear cualquier thread.

### 4.6 Simplificación del self-pipe (señales)

Los handlers tienen que ser **async-signal-safe**: un handler puede interrumpirme el programa
en cualquier instrucción, incluso con un lock tomado o en medio de un `malloc`. Por eso mi
handler **solo hace `setattr(estado, flag, True)`** y nada de trabajo pesado
([senales.py](src/senales.py)). El loop principal de la TUI chequea esos flags en cada tick
y ahí ejecuta la acción real (dump, releer config, toggle). Es mi **versión pragmática del
self-pipe**: en vez de escribir un byte a un pipe real, uso un flag que el loop poletea. Lo
decidí conscientemente y me alcanza para este loop (que ya despierta cada 0.1 s); un
self-pipe real me haría falta si el loop estuviera bloqueado en `select()` esperando y
tuviera que despertarlo con la señal.

### 4.7 Recolector y Agregador como procesos separados: por qué no

La consigna los lista como componentes. Decidí **no** crear un proceso recolector central que
reparta trabajo: cada analizador es autónomo y lee `/proc` para su dimensión. La ventaja es
menos acoplamiento y un punto de falla menos (si un analizador muere, los demás siguen — lo
verifiqué con `kill -9`). El costo es que cada analizador recorre `/proc` por su cuenta
(lecturas redundantes), pero para la escala de este TP es despreciable. El **Agregador** sí
existe, solo que no como código mío: es el **proceso servidor del `Manager`**, que es
literalmente el que "mantiene el snapshot global en memoria compartida".

## 5. Conceptos del curso aplicados

- **Proceso vs thread**: mi arquitectura principal es **multiproceso** (7 analizadores +
  display, cada uno con su espacio de memoria). El único **thread** que uso es el lector de
  teclado dentro del display ([display.py](src/display.py)): elegí un thread ahí porque pasa
  casi todo el tiempo **bloqueado en I/O** (`select`/`read` sobre stdin), donde el GIL se
  libera y no compite por CPU. Para el trabajo CPU-bound (leer y parsear `/proc`) uso
  procesos justamente para esquivar el GIL. *(Clases 8-10.)*
- **`/proc` y anatomía del proceso**: todo lo saco de `/proc/<pid>/stat`, `status`,
  `cmdline`, `maps`, `fd/`, `task/`. Por ejemplo, el campo `comm` de `stat` viene entre
  paréntesis y puede tener espacios, así que lo parseo buscando el último `)`
  ([procfs.py](src/procfs.py)). *(Clase 3.)*
- **Estados R/S/D/T/Z**: los leo del campo 3 de `stat` y los muestro en la vista Resumen. *(Clase 3.)*
- **Zombies**: en la vista Sistema cuento los procesos en estado `Z` — procesos que ya
  terminaron pero cuyo padre todavía no llamó a `wait()`, por eso siguen ocupando una entrada
  en la tabla de procesos. *(Clase 4: fork/exec/wait.)*
- **fork y Copy-on-Write**: al usar `fork`, los hijos comparten páginas con el padre hasta
  que alguno escribe; así heredo el snapshot y los `Value` sin copiarlos. *(Clase 4.)*
- **File descriptors**: en la vista FDs listo `/proc/<pid>/fd/` y resuelvo cada symlink con
  `readlink`, infiriendo el tipo (socket/pipe/tty/file). *(Clase 5.)*
- **Señales**: manejo el catálogo (INT/TERM/HUP/USR1/USR2), decodifico las máscaras hex de
  64 bits (`SigBlk`/`SigIgn`/`SigCgt`/…) bit a bit a nombres, y mis handlers son
  async-signal-safe. *(Clase 6.)*
- **Memoria compartida e IPC**: uso `Manager`, `Value` y `Lock`. *(Clases 7 y 9.)*
- **`fork` vs `spawn`**, **race conditions** y **locks**: ver *Decisiones de diseño*. *(Clases 9 y 11.)*
- **Scheduler**: en la vista Scheduling muestro `nice`, `priority`, `policy`
  (OTHER/FIFO/RR…), RT priority, afinidad y **context switches voluntarios vs
  involuntarios** (los CPU-bound acumulan involuntarios: el scheduler los desaloja al agotar
  su quantum). *(Clase 3 y teoría de scheduling.)*
- **PID vs TID**: en la vista Threads recorro `/proc/<pid>/task/<tid>/`; el thread principal
  tiene `TID == PID`. *(Clase 10: threads como LWPs.)*

## 6. Limitaciones conocidas

- **`SIGWINCH`** (repintar al redimensionar la terminal): no lo implementé. La consigna lo
  marca como opcional/recomendado.
- **Interacción de teclado solo con `docker compose run`**, no con `docker compose up`
  (ver *Cómo correr*).
- **Solo veo procesos del contenedor**: sin `pid: "host"` en el compose, el monitor ve los
  procesos de su propio namespace (el monitor + sus analizadores). Me alcanza para demostrar
  todo, pero no es "todo el host". Se puede ampliar agregando `pid: "host"`.
- **CPU% puede superar 100%**: es por core; un proceso multihilo puede pasar de 100%
  (convención tipo `htop`), no es un error.
- **No hice extensiones bonus** (histórico, detección de anomalías, árbol de procesos, etc.).
- **Lecturas redundantes de `/proc`**: cada analizador recorre `/proc` por su cuenta (ver
  4.7). No escala idealmente a miles de procesos, pero sí a las cargas de este TP.

## 7. Cómo testear

```bash
# 1. Correr con carga real y comparar contra ps dentro del contenedor
docker compose run --rm monitor sh
#   (dentro)
sleep 300 & yes > /dev/null &
python src/dia1_lister.py     # listado simple para contrastar
ps -eLf                        # comparar PID/PPID/estado/threads

# 2. Ver la arquitectura multiproceso "cruda" (datos de prueba)
python src/dia2_lister.py      # y en otra terminal: kill -9 <pid de un analizador>

# 3. Probar las señales del monitor (ver sección "Cómo correr")
```

## 8. Estructura del repositorio

```
TP1/
├── README.md              ← este archivo
├── Dockerfile             ← imagen Python 3.11 + procps
├── docker-compose.yml     ← tty/stdin_open, monta el repo en /app
├── requirements.txt       ← rich
├── config.json            ← intervalos por vista (recargable con SIGHUP)
└── src/
    ├── main.py            ← orquestador: analizadores + señales + TUI
    ├── procfs.py          ← todos los parsers de /proc
    ├── display.py         ← TUI (rich) + lectura de teclado en thread
    ├── senales.py         ← handlers de señales del monitor
    ├── analizadores/      ← 1 módulo por dimensión (7)
    │   ├── base.py        ← loop genérico de analizador
    │   ├── resumen.py  memoria.py  fds.py  threads.py
    │   └── senales.py  scheduling.py  sistema.py
    └── dia1_lister.py .. dia4_lister.py
                           ← snapshots de progreso por día (no son parte del
                             monitor final; los dejo como registro del desarrollo)
```

## 9. Decisiones sobre la TUI

Elegí **`rich`** sobre `curses` por velocidad de desarrollo: me da tablas y paneles decentes
con poco código. El layout lo dejé fijo: cabecera de estado, lista de procesos arriba, panel
de detalle abajo (que cambia según la vista) y pie con la ayuda breve. La lectura de teclado
la puse en un thread con la terminal en modo `cbreak` (deja `Ctrl+C` funcionando).

## 10. Lo que aprendí

*(A completar en primera persona: 2-3 párrafos sobre lo que descubrí haciendo el TP — por
ejemplo la diferencia real entre `Manager` y `Value`, por qué un handler no puede hacer
trabajo pesado, o qué sentí al ver un zombie aparecer en mi propio monitor.)*
