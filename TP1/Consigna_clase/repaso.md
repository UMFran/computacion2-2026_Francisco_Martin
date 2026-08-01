# Repaso conceptual — TP1 Monitor de Procesos y Threads

> Documento de estudio personal (no es parte de la entrega). Explica desde cero los
> conceptos que te van a preguntar en la corrección, con analogías y ligados a tu código.

## Índice
1. [Proceso, memoria y thread](#bloque-1)
2. [Ciclo de vida: fork, wait, zombies, estados](#bloque-2)
3. [Concurrencia y el GIL](#bloque-3)
4. [IPC y memoria compartida (Manager vs Value)](#bloque-4)
5. [Race conditions y locks](#bloque-5)
6. [Señales](#bloque-6)
7. [Scheduling](#bloque-7)
8. [/proc, PID vs TID y page faults](#bloque-8)

---

<a name="bloque-1"></a>
# Bloque 1 — Proceso, memoria y thread

## ¿Qué es un proceso?
Un **programa** es un archivo muerto en el disco (`main.py`). Un **proceso** es ese programa
**corriendo**: tiene un número de identidad (PID), memoria propia, y el kernel lo pone y saca
del CPU.

> El programa es la *receta escrita*. El proceso es *vos cocinándola ahora*, con tu cocina y
> tus manos ocupadas.

## La memoria de un proceso
Cada proceso tiene su memoria dividida en zonas. Pensala como una **casa con habitaciones**:

| Zona | Qué guarda | Analogía |
|------|-----------|----------|
| **text** (código) | las instrucciones del programa | el libro de recetas, no se modifica |
| **data / BSS** | variables globales | la despensa fija |
| **heap** | lo dinámico, crece hacia arriba | mesada donde vas apilando cosas |
| **stack** | variables locales y llamadas a funciones, crece hacia abajo | anotador temporal |

**Idea raíz de medio TP**: la memoria de un proceso es SUYA. El proceso A **no puede** tocar
la memoria del proceso B. Por eso, para compartir datos entre procesos hace falta un mecanismo
especial (IPC / `Manager` / `Value`). *(En tu monitor esto lo leés de `/proc/<pid>/maps`.)*

## Thread vs proceso
Un **thread** (hilo) es una línea de ejecución dentro de un proceso.

> - **Proceso** = una **casa**, con su memoria aislada de las demás.
> - **Threads** = las **personas dentro de esa casa**: comparten cocina, despensa y heap, pero
>   cada una tiene su propio anotador (stack).

| | Proceso | Thread |
|---|---|---|
| Memoria | propia y aislada | compartida con los threads del mismo proceso |
| Costo de crear | caro (casa nueva) | barato (una persona más) |
| Si uno rompe algo | no afecta a otros procesos | puede corromper la memoria compartida |
| Comunicación | necesita IPC | directa (ya comparten memoria) |

En tu TP: los 7 analizadores son **procesos**; el lector de teclado es un **thread** dentro del
display. El porqué está en el Bloque 3 (GIL).

---

<a name="bloque-2"></a>
# Bloque 2 — Ciclo de vida: fork, wait, zombies

## `fork()` — clonar un proceso
La única forma de crear un proceso en UNIX es que uno existente se **clone** con `fork()`. El
original es el **padre**, la copia el **hijo**.

> Apretás "fotocopiar" y sale una casa idéntica al lado. Desde ese instante son independientes.

- El hijo recibe un **PID** nuevo y conoce a su padre por el **PPID**.
- Esto arma un **árbol** de procesos; en la cima está el PID 1 (`init`/`systemd`).

## Copy-on-Write (COW) — por qué fork es barato
Al hacer `fork`, padre e hijo **comparten** las páginas de memoria como "solo lectura". Recién
**cuando alguno escribe** el kernel copia *esa* página. Mientras solo lean, no se copia nada.

> No fotocopiás la casa entera: comparten hasta que alguno quiera pintar una pared; ahí recién
> se copia esa pared.

*(Esto te deja heredar el snapshot y los `Value` sin pagar la copia.)*

## `exec()` — cambiar de programa
`fork` te da una copia del **mismo** programa. Para correr **otro**, el hijo llama a `exec()`,
que **reemplaza** su contenido por el nuevo programa (manteniendo el PID). El combo `fork`+`exec`
es cómo la shell ejecuta un comando.

## `wait()` — el padre cobra el certificado
Cuando un hijo termina no desaparece del todo: deja un recibo con su **código de salida**. El
padre lo recoge con `wait()`. Ahí sí el hijo se borra por completo.

> El hijo "muere", pero queda un **certificado de defunción** que solo el padre puede retirar.
> Hasta que no lo retira, sigue en el registro ocupando lugar.

## Zombie (estado Z) — la pregunta estrella
Un **zombie** es un proceso que **ya terminó** pero cuyo padre **todavía no llamó a `wait()`**.

- **No usa** memoria ni CPU (está muerto).
- Pero **sigue ocupando una entrada** en la tabla de procesos (su PID sigue reservado), porque
  su código de salida espera ser retirado.
- Por eso lo **seguís viendo en `/proc`**: no ves el proceso vivo, ves el recibo sin cobrar.
- Se limpia cuando el padre hace `wait()`. Si el padre muere antes, lo **adopta el PID 1**, que
  hace `wait()` por él.

> La confusión típica: "si terminó, ¿por qué está?". Porque **terminar** y **ser borrado de la
> tabla** son dos cosas distintas, y entre medio hay un paso que depende del padre.

## Estados R/S/D/T/Z (campo 3 de `/proc/<pid>/stat`)

| Estado | Nombre | Significado | Analogía |
|--------|--------|-------------|----------|
| **R** | Running/Runnable | usando el CPU o listo para usarlo | cocinando activamente |
| **S** | Sleep interrumpible | esperando algo, se despierta fácil | atento al timer |
| **D** | Sleep ininterrumpible | esperando I/O de disco, no se lo despierta ni con señales | metido en el horno |
| **T** | sTopped | pausado (`SIGSTOP`/debugger) | congelado |
| **Z** | Zombie | terminó, espera el `wait()` del padre | certificado sin cobrar |

**Verlo en vivo:** `sleep 60 &` (queda **S**), `yes >/dev/null &` (queda **R**), y mirá con
`ps -o pid,ppid,state,comm`.

---

<a name="bloque-3"></a>
# Bloque 3 — Concurrencia y el GIL

## Concurrencia vs paralelismo
- **Concurrencia**: varias tareas *en progreso* que se van turnando (un cocinero atendiendo tres
  ollas, saltando entre ellas).
- **Paralelismo**: varias tareas *ejecutándose al mismo tiempo* de verdad (tres cocineros, uno
  por olla). Requiere varios cores.

## El GIL (Global Interpreter Lock)
En CPython (el Python estándar) hay un **candado global**: **solo un thread puede ejecutar
bytecode de Python a la vez**. Aunque tengas 8 cores y 8 threads, los threads de Python **se
turnan**, no corren en paralelo de verdad.

> Es como una **cocina con una sola cuchara**: puede haber varias personas, pero para revolver
> hay que tener la cuchara, y hay una sola. Se la van pasando.

¿Por qué existe? Para simplificar el manejo interno de memoria de CPython (el conteo de
referencias no es thread-safe); el GIL lo protege de una.

## La consecuencia clave
- Para trabajo **CPU-bound** (calcular, parsear): los threads **no aceleran**, se turnan la
  cuchara. Ahí conviene **procesos**: cada proceso tiene su **propio intérprete y su propio
  GIL** → paralelismo real.
- Para trabajo **I/O-bound** (esperar disco, red, teclado): cuando un thread se **bloquea
  esperando I/O, suelta el GIL**. Entonces los threads **sí** sirven: mientras uno espera, otro
  usa la cuchara.

## Aplicado a tu TP (pregunta del Día 4)
- Los **analizadores** parsean `/proc` → **CPU-bound** → los hice **procesos** para esquivar el
  GIL y que corran en paralelo de verdad.
- El **lector de teclado** pasa casi todo el tiempo **bloqueado** en `select`/`read` esperando
  una tecla → **I/O-bound** → ahí un **thread** está perfecto: mientras espera, suelta el GIL y
  no le roba CPU a nadie. Además es barato (no necesito una "casa" nueva para esperar una tecla).

---

<a name="bloque-4"></a>
# Bloque 4 — IPC y memoria compartida (Manager vs Value)

## El problema
Del Bloque 1: **los procesos no comparten memoria**. Entonces, ¿cómo hacen los 7 analizadores
para publicar sus datos y que el display los lea? Necesitás **IPC** (Inter-Process
Communication): mecanismos que el sistema operativo provee para pasar datos entre procesos.

## Las herramientas de `multiprocessing`
| Herramienta | Qué es | Para qué sirve |
|-------------|--------|----------------|
| `Pipe` | un caño de dos puntas entre dos procesos | mandar mensajes 1-a-1 |
| `Queue` | una cola FIFO segura entre procesos | productor-consumidor (una lista de mensajes) |
| `Value` / `Array` | memoria compartida cruda (mmap) para tipos simples | compartir un escalar o vector rápido |
| `Manager` | un **proceso servidor** que guarda objetos Python | compartir dicts/listas complejas |

## Cómo funciona el `Manager` (pregunta del Día 3)
Cuando hacés `Manager().dict()`, se levanta **un proceso aparte** (el "servidor") que es el que
**realmente** tiene el diccionario. Vos, desde los otros procesos, tenés un **proxy** (un
representante). Cuando hacés `snapshot["memoria"] = {...}`:

1. Ese dato se **serializa (pickle)** y **viaja** como un mensaje al proceso servidor.
2. El servidor hace el cambio real en SU memoria.
3. Como el servidor atiende **un pedido a la vez**, las escrituras quedan **serializadas** → aunque
   7 analizadores escriban "al mismo tiempo", el servidor las ordena → **no se corrompe**.

> El `Manager` es como un **secretario** con un cuaderno. Nadie escribe en el cuaderno
> directamente: todos le dictan al secretario, y él anota de a uno. Por eso nunca se pisan.

Costo: cada acceso es un viaje ida-y-vuelta + pickle → **más lento**, pero **flexible** (guarda
cualquier objeto anidado).

## Cómo funciona `Value`
`Value('d', 2.0)` reserva un pedacito de **memoria compartida real (mmap)** que todos los
procesos **mapean** en su espacio. Leer/escribir es acceso directo a memoria → **rapidísimo**.
Limitación: solo tipos C simples (un `double`, un `int`), nada de estructuras.

## Manager vs Value — el tradeoff (pregunta estrella)
| | `Manager.dict` | `Value` |
|---|---|---|
| Guarda | estructuras complejas y anidadas | un escalar de tipo simple |
| Cómo | proceso servidor + pickle + mensajes | memoria compartida cruda (mmap) |
| Velocidad | más lento | rapidísimo |
| Cuándo | el **snapshot** (7 claves con dicts que crecen) | el **intervalo** y el **flag verbose** |

**Tu justificación**: el snapshot es una estructura grande y variada → `Manager`. El intervalo es
un solo `float` que el display escribe seguido y el analizador lee en cada vuelta → `Value` (sería
absurdo levantar todo un servidor para un número).

**¿Por qué no `Queue`/`Pipe`?** Tu patrón es "cada analizador mantiene el **último** valor de su
clave y el display lo mira cuando quiere" (estado más reciente). Una cola sirve para *no perder
mensajes* (un flujo de eventos); acá no querés acumular datos viejos, querés el actual. Por eso el
dict compartido encaja mejor.

## `fork` vs `spawn` vs `forkserver` (pregunta del Día 2)
Son las tres formas de arrancar un proceso hijo:

- **`fork`** (default en Linux): el hijo es una **copia** del padre (con COW). **Hereda todo**:
  archivos abiertos, locks, los proxies del Manager, los `Value` y hasta los *closures*. Barato.
  Contra: si el padre tenía threads, el hijo hereda su estado a medio-camino y puede haber
  problemas (por eso conviene forkear **antes** de crear threads — que es lo que hacés).
- **`spawn`** (default en Windows/Mac): arranca un intérprete **nuevo y limpio**, **reimporta** el
  módulo y te pasa los argumentos **pickleándolos**. No hereda la memoria del padre. Más lento, y
  los argumentos tienen que ser picklables (**un closure no lo es** → tu `crear_recolector(...)`
  fallaría).
- **`forkserver`**: un proceso servidor forkea hijos limpios a pedido. Punto medio.

**Tu elección**: `fork`, para heredar el `Manager`, los `Value`, el `Lock` y los closures sin
picklear ni reimportar.

---

<a name="bloque-5"></a>
# Bloque 5 — Race conditions y locks

## ¿Qué es una race condition?
Es cuando el **resultado depende del orden impredecible** en que se intercalan dos operaciones
concurrentes. "Corren una carrera" (race) y según quién llega primero, el resultado cambia.

## El ejemplo clásico: `x += 1` (pregunta del Día 2)
Parece **una** operación, pero en realidad son **tres**:

1. **Leer** el valor de `x` (ej: 5)
2. **Sumar** 1 (6)
3. **Escribir** el resultado en `x`

A nivel de **bytecode** son instrucciones separadas (`LOAD`, `ADD`, `STORE`), y el scheduler
puede **cambiar de thread/proceso en el medio**. Si dos hacen `x += 1` a la vez:

```
proceso A: lee x=5 ......................... escribe 6
proceso B: ........... lee x=5 ... escribe 6
```

Los dos leyeron 5, los dos escribieron 6. **Se perdió un incremento** (debería ser 7). Por eso,
aunque escribas un solo `+=`, **no es atómico** → es una race.

## El lock (sección crítica)
Un **lock** (mutex) es un **token**: solo quien lo tiene puede entrar a la "sección crítica". Con
`with lock:` garantizás que **uno a la vez** haga el leer-modificar-escribir → no se pierden
incrementos.

> Es la **cuchara** de nuevo: para tocar la olla compartida tenés que tener la cuchara; hay una
> sola, así que nadie te pisa mientras la tenés.

## Aplicado a tu TP (preguntas Días 2 y 5)
- **Entre analizadores NO hay race**: cada uno escribe **solo su propia clave** (`snapshot[nombre]
  = {...}`) y, además, el Manager serializa cada escritura. Nunca dos tocan la misma clave → no
  hace falta lock entre ellos.
- **El dump SÍ usa lock**: para volcar las 7 claves juntas y coherentes (SIGUSR1), tomo el `Lock`
  mientras copio; como todos escriben bajo ese mismo lock, nadie escribe en el medio → la foto es
  consistente. La copia va **dentro** del lock (rápida); el `json.dump` a disco va **afuera**
  (lento), para no frenar a los 7 analizadores mientras escribo el archivo.

> **Ojo, matiz importante**: `snapshot[k] = {...}` es atómico (un pedido al servidor). Lo que el
> lock protege no es *una* escritura, sino **leer las 7 de una** sin que nadie las cambie en el
> medio.

---

<a name="bloque-6"></a>
# Bloque 6 — Señales

## ¿Qué es una señal?
Una **señal** es una notificación **asincrónica** que el kernel le entrega a un proceso: "pasó
algo". Interrumpe lo que el proceso esté haciendo para avisarle.

> Es un **golpecito en el hombro** en medio de tu tarea. Tenés que decidir qué hacés: seguir,
> parar, o atender.

## Catálogo (las que importan)
| Señal | Qué avisa / hace |
|-------|------------------|
| `SIGINT` | Ctrl+C (interrumpir) |
| `SIGTERM` | pedido "amable" de terminar |
| `SIGKILL` | matar **a la fuerza** (no se puede atrapar) |
| `SIGSTOP` | pausar (no se puede atrapar) |
| `SIGHUP` | "colgó la terminal"; por convención se usa para **recargar config** |
| `SIGUSR1` / `SIGUSR2` | libres, para lo que quieras (vos: dump y verbose) |
| `SIGCHLD` | un hijo cambió de estado (terminó) |

Ante una señal, por defecto el proceso hace algo (terminar, ignorar, parar…). Vos podés instalar
un **handler**: una función tuya que corre en vez de la acción por defecto.

## `SIGKILL` y `SIGSTOP` no se pueden atrapar (pregunta del Día 3)
El kernel **no te deja** ponerles handler, bloquearlas ni ignorarlas. Es a propósito: siempre
tiene que existir una forma de **matar o pausar** un proceso que se volvió loco. Consecuencia para
tu "shutdown limpio": funciona con `SIGINT`/`SIGTERM`, pero contra `SIGKILL` no hay nada que hacer
(te matan sin chance de limpiar).

## Bloqueadas / ignoradas / con handler (las máscaras)
En `/proc/<pid>/status` hay máscaras que dicen qué hace el proceso con cada señal:
- `SigBlk` = **bloqueadas** (diferidas hasta desbloquear).
- `SigIgn` = **ignoradas**.
- `SigCgt` = **capturadas** (tienen handler propio).

Son **números hexadecimales de 64 bits**: cada **bit** representa una señal. El **bit i** (desde
0) corresponde a la **señal i+1**. Para decodificar `SigCgt: ...4002`: lo pasás a binario y por
cada bit en 1 mirás qué señal es. *(En tu código: `procfs.decodificar_mascara`.)*

## async-signal-safe: por qué el handler no hace trabajo pesado (pregunta del Día 3)
El handler puede interrumpir tu programa **en cualquier instrucción**, incluso **mientras tenías
un lock tomado** o estabas **en medio de un `malloc`**. Si adentro del handler hacés algo que
necesita ese mismo lock (o que pide memoria, o imprime), **se traba (deadlock)** o se corrompe.

> Es como si el golpecito en el hombro te llega justo cuando tenías las dos manos adentro del
> motor. Si en ese momento te pedís a vos mismo las manos que ya tenés ocupadas, te quedás trabado.

**Regla**: en el handler, **lo mínimo** (prender un flag). El trabajo real lo hace el loop
principal después. *(Es lo que hacés: el handler solo hace `setattr(estado, flag, True)`.)*

## Self-pipe vs tu flag (pregunta del Día 3)
El **self-pipe** clásico: el handler escribe **1 byte a un pipe**, y el loop principal vigila ese
pipe con `select()`. Sirve para **despertar** un loop que está **bloqueado** esperando.

Tu **simplificación**: en vez de un pipe real, prendés un **flag** que el loop **poletea** en cada
vuelta. Funciona porque tu loop **ya despierta cada 0.1 s**. El self-pipe real haría falta si el
loop estuviera **dormido en `select()`** esperando input y necesitaras que la señal lo despierte
(un flag no despierta un `select()` bloqueado).

## PID 1 y señales (pregunta del Día 3)
El kernel trata al **PID 1 distinto**: **no aplica las acciones por defecto** de las señales que
PID 1 **no** tenga con handler. O sea: una señal **sin handler** llega a PID 1 y **se ignora**
(un proceso normal, en cambio, moriría). Es lo que hace `init`/`systemd`: por eso registra sus
handlers explícitamente.

> **Ojo con tu setup**: al agregar `pid: "host"` en el compose, tu monitor **ya no es PID 1**
> (es un proceso normal con un PID del host), así que las señales le funcionan "normal". El caso
> de PID 1 aplicaba a la versión **sin** `pid: "host"` (cuando el monitor era PID 1 del
> contenedor): ahí, si no registrabas el handler de SIGINT, el Ctrl+C no habría hecho nada. El
> concepto igual hay que saberlo.

---

<a name="bloque-7"></a>
# Bloque 7 — Scheduling

## ¿Qué es el scheduler?
Hay muchos procesos y pocos cores. El **scheduler** del kernel decide **quién usa el CPU y por
cuánto tiempo**, turnándolos tan rápido que parece que corren todos a la vez.

## nice y priority
- **nice**: qué tan "amable" es el proceso, de **-20** (egoísta, más prioridad) a **+19** (amable,
  menos prioridad). Más nice = cede más el CPU.
- **priority**: el valor que el kernel usa internamente, derivado del nice.

## Políticas (pregunta del Día 3)
| Política | Qué es |
|----------|--------|
| **OTHER** (CFS) | la normal, de tiempo compartido y "justa". **Casi todo** usa esta. |
| **FIFO** | tiempo real: prioridad fija, corre hasta que cede solo. Necesita privilegios; raro. |
| **RR** | tiempo real con quantum (round-robin entre los de igual prioridad). Raro. |
| **BATCH / IDLE** | para tareas de fondo. |

Por eso en tu monitor **casi todo aparece como OTHER**: las de tiempo real son para casos
especiales (audio, control industrial) y requieren permisos.

## Context switches: voluntario vs involuntario (pregunta estrella)
Un **context switch** es cuando el kernel **guarda el estado** de un proceso y **carga** el de
otro (cambia quién está en el CPU).

- **Voluntario**: el proceso **cede** el CPU por su cuenta, típicamente porque **se pone a esperar
  algo** (I/O, un `sleep`). "Por ahora no tengo nada que hacer, seguí vos."
- **Involuntario**: el scheduler lo **desaloja a la fuerza** porque **se le acabó el quantum** o
  porque llegó algo más prioritario. "Se te acabó el turno."

**Por qué un CPU-bound (`yes`) acumula involuntarios**: nunca se pone a esperar nada (siempre tiene
trabajo), así que **nunca cede voluntariamente** → el scheduler lo tiene que **echar** cada vez
que se le acaba el quantum → montón de switches **involuntarios**. Un proceso I/O-bound, al revés,
cede seguido (voluntarios).

## utime / stime y cómo calculás CPU%
- **utime**: tiempo de CPU en **modo usuario** (tu código).
- **stime**: tiempo en **modo kernel** (syscalls).
- Se miden en **jiffies** (`CLK_TCK` por segundo, normalmente 100).
- **CPU%** = cuánto creció `utime+stime` entre dos lecturas, dividido por el tiempo real
  transcurrido. Por eso tomás **dos muestras** separadas por un intervalo. Como es por core, un
  proceso multihilo puede pasar de 100%.

---

<a name="bloque-8"></a>
# Bloque 8 — /proc, PID vs TID y page faults

## ¿Qué es `/proc`?
Un **filesystem virtual**: no son archivos reales en disco, el kernel los **genera al leerlos**.
Cada proceso tiene una carpeta `/proc/<pid>/` con archivos que exponen su estado interno:

| Archivo | Qué te da |
|---------|-----------|
| `stat` | estado, PPID, jiffies de CPU, threads, nice, policy… (por posición) |
| `status` | lo mismo en formato `clave: valor` (UID, VmRSS, señales, ctx switches…) |
| `cmdline` | la línea de comando (args separados por `\0`) |
| `maps` | los segmentos de memoria (text/data/heap/stack) |
| `fd/` | los file descriptors abiertos (symlinks a su destino) |
| `task/` | una carpeta por **thread** |

## PID vs TID (pregunta del Día 3)
Un **proceso** (PID) tiene uno o más **threads**, y cada thread tiene su **TID**. En Linux los
threads son **LWPs** (lightweight processes) y aparecen en `/proc/<pid>/task/<tid>/`. El **thread
principal** tiene **`TID == PID`**. Un proceso de un solo hilo tiene una sola carpeta en `task/`
(la suya). *(Tu vista Threads recorre justamente `task/`.)*

## Page faults minor vs major (pregunta del Día 3)
Un **page fault** ocurre cuando el proceso accede a memoria que **no está mapeada** en ese momento:
- **Minor**: la página **ya está en RAM**, solo falta enlazarla al proceso (ej: una librería
  compartida ya cargada, o una página COW). **Rápido, no toca disco.**
- **Major**: la página hay que **traerla del disco** (swap, o un archivo todavía no cargado).
  **Lento.**

Por eso un proceso **recién arrancado** acumula **muchos minor** (va mapeando sus páginas a medida
que las toca) y **casi ningún major**.

---

## Cómo usar este documento
Leélo una vez entero para tener el mapa, y después andá a los bloques de las preguntas que te
cuesten. Cuando te sientas listo, pedime el **simulacro**: te tiro las preguntas de a una y donde
trabes volvemos al bloque correspondiente.
