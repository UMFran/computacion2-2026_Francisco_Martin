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

**Para usar la TUI (recomendado):**

```bash
docker compose run --rm --build monitor
```

Este es el comando correcto para una interfaz de terminal: conecta una terminal
**del tamaño convencional**, así las columnas se ven completas, no parpadea y **el teclado
funciona** (cambiar de vista, navegar, filtrar, etc.). La primera vez también buildea.

> **¿Por qué no `docker compose up`?** `up` está pensado para servicios/logs, no para
> apps interactivas: le da al contenedor una terminal chica por defecto (~80 columnas) que
> no se sincroniza con la tuya, así que las columnas quedan apretadas e ilegibles, la pantalla
> parpadea y las teclas no responden. Sirve para *buildear* (`docker compose up --build`) o
> para ver el dashboard de reojo, pero para **usar** la TUI andá con `run`.

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

La forma más simple: mandarle la señal **por nombre de servicio**, sin averiguar ningún
PID. Parado en la carpeta del TP1, con el monitor corriendo en segundo plano:

```bash
docker compose up -d --build             # arranca el monitor en segundo plano
docker compose kill -s SIGUSR1 monitor   # dump del snapshot a dump_<timestamp>.json
docker compose kill -s SIGUSR2 monitor   # toggle modo verbose
docker compose kill -s SIGHUP  monitor   # releer config.json (intervalos)
docker compose kill -s SIGTERM monitor   # shutdown limpio (igual que SIGINT / Ctrl+C)
docker compose down                       # apagar todo
```

`docker compose kill -s` **no mata**: manda la señal que le indiques al proceso del
monitor. (Si querés *ver la TUI reaccionar* en vivo, corré la TUI con
`docker compose run --rm monitor` en una terminal y mandá las señales desde otra.)

## 3. Arquitectura

```
        ┌───────────────┐   lista los PIDs de /proc cada 1s y
        │  RECOLECTOR   │   los reparte a los analizadores por Queue
        └───────┬───────┘
                │  (una Queue por analizador)
   ┌────────┬───┴────┬────────┬────────┬────────┬────────┐
┌──▼─────┐┌─▼─────┐┌─▼──┐┌────▼┐┌──────▼┐┌───────▼┐┌───────▼┐
│Resumen ││Memoria││FDs ││Thr  ││Señales││Sched   ││Sistema │  (7 analizadores)
│  2s    ││  3s   ││ 5s ││ 2s  ││  10s  ││  10s   ││  2s    │  leen /proc (datos
└──┬─────┘└─┬─────┘└─┬──┘└──┬──┘└───┬───┘└───┬────┘└───┬────┘  de su dimensión)
   │ escriben SU clave (with lock solo para el dump)   │
   └────────┴────────┴───┬────┴───────┴────────┴───────┘
                         ▼
        ┌──────────────────────────────────────────────┐
        │        SNAPSHOT GLOBAL  (Manager.dict)         │
        │   lo posee el proceso servidor del Manager     │
        │   "resumen" "memoria" "fds" ... "sistema"      │
        └───────────────────────┬────────────────────────┘
                                 │ lee (polling)
                                 ▼
                    ┌──────────────────────────┐
                    │        DISPLAY (TUI, rich) │
                    │  + thread de teclado       │
                    │  +/- escribe al Value      │
                    │      del intervalo ────────┼──▶ (a cada analizador)
                    └──────────────────────────┘

   Proceso principal = DISPLAY + MANEJADOR DE SEÑALES.
   Señales INT/TERM/HUP/USR1/USR2 → el handler solo prende un flag;
   el loop de la TUI lee el flag y ejecuta la acción real.
```

### Componentes

| Componente | Cómo lo resolví | Archivo |
|------------|-----------------|---------|
| **Recolector** | Un proceso dedicado lista los PIDs de `/proc` cada 1s y los reparte a los 7 analizadores por `Queue` (una por analizador). Los analizadores ya no descubren procesos por su cuenta. | [`recolector.py`](src/recolector.py) |
| **7 analizadores** | Un proceso independiente por dimensión, todos corriendo un loop genérico común; leen `/proc` solo para los datos de su dimensión, sobre los PIDs que el recolector reparte. | [`analizadores/`](src/analizadores/) |
| **Agregador** | Lo cumple el **proceso servidor del `Manager`**: es el único que posee el dict y serializa todas las escrituras. No armé un proceso agregador aparte porque el Manager ya cumple ese rol. | (Manager) |
| **Display (TUI)** | Renderiza la vista activa leyendo el snapshot; lee el teclado en un thread. | [`display.py`](src/display.py) |
| **Manejador de señales** | Handlers async-signal-safe que solo prenden flags. | [`senales.py`](src/senales.py) |

## 4. Decisiones de diseño

### 4.1 IPC que elegí para cada comunicación

| Comunicación | Mecanismo | Por qué lo elegí |
|--------------|-----------|------------------|
| Recolector → analizadores (lista de PIDs) | **`Queue`** (una por analizador) | Es un reparto de trabajo productor→consumidores: el recolector "empuja" la lista de PIDs a cada analizador. Es exactamente para lo que sirve una `Queue`. |
| Analizadores → snapshot global | **`Manager().dict()`** | Es una estructura anidada, con muchos escritores (7) y un lector; el proxy del Manager serializa el acceso a través de su proceso servidor y soporta valores complejos (dicts, listas). |
| Display → analizador (cambiar intervalo) | **`Value('d')`** por analizador | Es un escalar de alta frecuencia; `Value` es memoria compartida cruda (mmap), sin pasar por el servidor del Manager ni picklear nada. Un `Manager.dict` acá sería carísimo para un solo float. |
| Toggle verbose (SIGUSR2) → analizadores | **`Value('i')`** compartido | Igual que arriba: un flag entero simple, de lectura frecuente. |
| Coordinación de escritura para el dump | **`Lock`** | Ver *race conditions*. |

**¿Por qué `Queue` para el recolector pero `Manager.dict` para el snapshot?** Son dos patrones
distintos. El recolector→analizadores es *productor-consumidor* (repartir una lista): la `Queue`
encaja. El snapshot es *"último estado"*: cada analizador mantiene el último valor de su clave y
el display lo mira cuando quiere. Para "último estado" un dict compartido es mejor que una cola:
no se acumulan mensajes viejos y el lector siempre ve el valor actual. `Pipe` no lo usé porque la
`Queue` ya me resuelve el reparto a varios consumidores (un pipe es punto a punto).

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

### 4.7 Recolector y Agregador

- **Recolector**: es un proceso propio ([recolector.py](src/recolector.py)) que lista los PIDs
  de `/proc` una vez por ciclo y los reparte a los 7 analizadores por `Queue`. Así centralizo el
  descubrimiento de procesos (antes cada analizador listaba `/proc` por su cuenta, con lecturas
  redundantes) y cumplo el rol de "distribuir trabajo a los analizadores" de la consigna.
  - *Tradeoff que asumí*: el recolector es un **punto único de falla**. Lo resolví con
    **degradación elegante**: si el recolector muere, los analizadores **no se caen** — reusan la
    última lista de PIDs que recibieron y siguen actualizando datos (lo verifiqué con `kill -9`
    al recolector: el monitor siguió vivo). Y si muere un analizador, los demás siguen igual.
- **Agregador**: no es código mío, es el **proceso servidor del `Manager`**, que es literalmente
  el que "mantiene el snapshot global en memoria compartida" y serializa las escrituras de los 7
  analizadores.

## 5. Conceptos del curso aplicados

- **Proceso vs thread**: mi arquitectura principal es **multiproceso** (recolector + 7
  analizadores + display, cada uno con su espacio de memoria). El único **thread** que uso es el lector de
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
- **En Docker Desktop veo la VM Linux, no Windows**: con `pid: "host"` el monitor ve los
  procesos de todo el host. En Linux nativo eso es el sistema completo (como `htop`); en
  Docker Desktop (Windows/Mac) el "host" es la VM de LinuxKit, así que se ven sus procesos
  (bastantes menos). Para leer FDs y segmentos de memoria de procesos ajenos agrego la
  capability `SYS_PTRACE` en el compose.
- **CPU% puede superar 100%**: es por core; un proceso multihilo puede pasar de 100%
  (convención tipo `htop`), no es un error.
- **No hice extensiones bonus** (histórico, detección de anomalías, árbol de procesos, etc.).
- **El recolector es un punto único de falla** (mitigado): el descubrimiento de PIDs está
  centralizado en un solo proceso; si muere, los analizadores reusan la última lista y siguen
  (degradación elegante, ver 4.7). Cada analizador igual lee `/proc` para los *datos* de su
  dimensión, así que a miles de procesos no escala idealmente, pero sí a las cargas de este TP.

## 7. Cómo testear

```bash
# 1. Correr con carga real y comparar contra ps dentro del contenedor
docker compose run --rm monitor sh
#   (dentro) generá procesos y compará lo que muestra el monitor contra ps:
sleep 300 & yes > /dev/null &
ps -eLf                        # PID/PPID/estado/threads del sistema

# 2. Probar las señales del monitor (ver sección "Cómo correr")

# 3. Resiliencia: con el monitor corriendo, matá un analizador (o el recolector)
#    con `kill -9 <pid>` desde otra terminal y verificá que el monitor sigue vivo.
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
    ├── main.py            ← orquestador: recolector + analizadores + señales + TUI
    ├── recolector.py      ← proceso que lista PIDs y los reparte por Queue
    ├── procfs.py          ← todos los parsers de /proc
    ├── display.py         ← TUI (rich) + lectura de teclado en thread
    ├── senales.py         ← handlers de señales del monitor
    ├── analizadores/      ← 1 módulo por dimensión (7)
    │   ├── base.py        ← loop genérico de analizador
    │   ├── resumen.py  memoria.py  fds.py  threads.py
    │   └── senales.py  scheduling.py  sistema.py
    └── progreso/          ← dia1_lister.py .. dia4_lister.py: snapshots por día
                             para ver el avance del desarrollo. NO son parte del
                             monitor (el monitor funciona sin esta carpeta).
```

## 9. Decisiones sobre la TUI

Elegí **`rich`** sobre `curses` por velocidad de desarrollo: me da tablas y paneles decentes
con poco código. El layout lo dejé fijo: cabecera de estado, lista de procesos arriba, panel
de detalle abajo (que cambia según la vista) y pie con la ayuda breve. La lectura de teclado
la puse en un thread con la terminal en modo `cbreak` (deja `Ctrl+C` funcionando).

## 10. Lo que aprendí

La idea que me ordenó todo el trabajo fue una que al principio no dimensionaba: **los procesos
no comparten memoria**. Empecé con un script de un solo proceso que leía `/proc`, y pasar a una
arquitectura multiproceso me obligó a entender que, para que siete procesos publicaran datos y
otro los leyera, hacían falta mecanismos de comunicación específicos. Ahí terminé de entender por
qué existen `Manager`, `Value` o `Queue` y cuándo conviene cada uno: no es lo mismo compartir una
estructura grande que crece (el snapshot, con `Manager` y su proceso servidor) que un solo número
que se lee todo el tiempo (el intervalo, con `Value` en memoria compartida). Esa distinción —qué
se guarda y, sobre todo, cómo viaja el dato: un mensaje serializado al servidor, o memoria
compartida por `mmap`— la tuve que precisar durante el desarrollo; era algo que usaba sin tener
del todo claro el mecanismo por debajo.

Lo segundo que me llevo es que **el código puede parecer correcto y esconder un problema serio**.
Un `contador += 1` se ve inofensivo hasta que entendés que son tres pasos (leer, sumar, escribir)
y que el scheduler puede cortar en el medio: ahí aparece la race condition. Con las señales me
pasó algo parecido: al principio mezclaba por qué el handler tiene que ser mínimo, y lo reafirmé
cuando entendí que la razón es la reentrancia —un handler te interrumpe en cualquier instrucción
y, si hace trabajo pesado que toma un recurso ya ocupado, te traba—. Entender el *porqué*, y no
solo la receta, es lo que me terminó de dar seguridad para defender cada decisión.

Por último, buena parte del TP fue **ver la teoría funcionando en `/proc`**. Algunos conceptos ya
los tenía claros de entrada —qué es un zombie, los estados de proceso, por qué matar un proceso no
arrastra a los demás—; otros los afiancé recién al verlos con datos reales: por qué un proceso
CPU-bound acumula context switches involuntarios, la diferencia entre un page fault minor y uno
major, o por qué el lector de teclado puede ser un thread (está bloqueado en I/O y suelta el GIL)
mientras los analizadores tienen que ser procesos. Conectar cada parte del código con eso es lo
que le dio sentido al TP completo.

**Trabajar con IA.** Una parte importante del aprendizaje fue *cómo* usé la IA. La consigna
proponía usarla como tutor y no como generador de código, y eso cambió mi forma de trabajar: en
vez de pegar lo que me tiraba, me acostumbré a preguntar el porqué de cada decisión y a defenderla
con mis palabras. Varias veces eso sirvió para corregir cosas —por ejemplo, cuando confundí `mmap`
con "DMA", o cuando mezclé por qué un handler de señales tiene que ser mínimo—: entenderlo mal, que
me lo marcaran y reformularlo yo mismo me dejó el concepto más firme que si lo hubiera copiado bien
de una. También aprendí a no dar todo por sentado: revisar contra la consigna, verificar que lo que
"andaba" realmente cumpliera, y frenar cuando algo no me cerraba en lugar de avanzar. Me quedo con
que la IA es una herramienta potente para aprender, siempre que uno mantenga el control de entender
lo que hace su propio código.
