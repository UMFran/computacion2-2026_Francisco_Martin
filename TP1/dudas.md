# Dudas y puntos de comprensión — TP1 Monitor de Procesos

Este archivo junta las **dudas que me fueron quedando** durante el desarrollo y los
**puntos donde tuve que precisar o corregir mi comprensión**. Lo incluyo por honestidad
intelectual: no todo lo entendí a la primera, y varias cosas las afiancé sobre la marcha.

---

## Dudas que me quedaron abiertas

1. **¿El `Manager.dict` se vuelve un cuello de botella a escala?**
   Todas las escrituras de los 7 analizadores pasan por un único proceso servidor. Con las
   cargas de este TP no se nota, pero me quedó la duda de a partir de cuántos procesos/analizadores
   ese servidor empieza a ser el límite, y de cómo lo mediría.

2. **Self-pipe vs mi flag: ¿hay algún caso real en *este* monitor donde el flag pierda?**
   Entendí que un flag no despierta un `select()` bloqueado y que el self-pipe real sí. Como mi
   loop se despierta solo cada 0.1 s, el flag me alcanza. Me quedó la duda de si existe algún
   escenario concreto en mi diseño actual donde el flag falle y el self-pipe sea imprescindible.

3. **`pid: "host"` y por qué en Docker Desktop el "host" es una VM.**
   Con `pid: "host"` el monitor ve los procesos del host. Entendí que en Docker Desktop (Windows)
   ese host es la VM Linux (LinuxKit), no Windows. Me quedó la duda de por qué Docker corre una VM
   en Windows y qué implicancias de permisos/seguridad tiene compartir el namespace de PID del host.

4. **`docker compose up` no reenvía las teclas a la TUI.**
   Terminé usando `docker compose run` para la parte interactiva. Me quedó la duda de si es una
   limitación inherente de `up` o si hay alguna forma de que `up` conecte una terminal interactiva
   del tamaño correcto.

5. **CPU% > 100 %.**
   Lo dejé con la convención de `htop` (es por core, así que un proceso multihilo puede pasar de
   100 %). Me quedó la duda de si sería "más correcto" normalizar dividiendo por la cantidad de
   cores, o si la convención por-core es la estándar.

6. **Page faults de procesos hijos (`cminflt`/`cmajflt`).**
   Muestro minor/major del proceso (campos 10 y 12 de `stat`). La consigna dice "campos 10-13",
   que incluye también los de los hijos (11 y 13). Me quedó la duda de si con minor/major alcanza
   o si convendría agregar los de hijos.

7. **SIGWINCH.**
   No lo implementé: como `rich` redibuja el frame completo en cada tick, el redimensionado de la
   terminal se corrige solo en el refresco siguiente. Me quedó la duda de si eso es suficiente o si
   un handler de SIGWINCH haría una diferencia real.

---

## Puntos que marcaron mi comprensión (cosas que precisé o corregí)

1. **`Value` usa memoria compartida (`mmap`), no "DMA".**
   En un momento dije que `Value` usaba DMA. Aprendí que DMA es un concepto de hardware (que un
   periférico acceda a la RAM sin pasar por el CPU) y no tiene que ver acá: lo que usa `Value` es
   memoria compartida por `mmap`, que los procesos mapean en su propio espacio de direcciones.

2. **Por qué el handler de señales debe ser mínimo: reentrancia, no rendimiento.**
   Al principio mezclaba la razón (pensaba que era "para no frenar a los analizadores"). La razón
   real es la reentrancia: el handler te interrumpe en cualquier instrucción, y si adentro hace
   trabajo pesado que toma un recurso ya ocupado (un lock, memoria), se traba (deadlock). Por eso
   solo prende un flag y el trabajo real lo hace el loop principal.

3. **Un zombie ya terminó; no es un proceso "dormido esperando".**
   Me costó distinguir el estado S del Z. Entendí que en S el proceso está vivo, espera algo y va a
   seguir ejecutando; un zombie, en cambio, ya terminó su ejecución para siempre y solo espera a que
   el padre retire su código de salida (`wait()`) para desaparecer de la tabla de procesos.

4. **`kill -9`: no es lo mismo matar un analizador que matar el Manager.**
   Al principio no me cerraba. Entendí que matar un analizador afecta a uno solo (son procesos
   independientes, no dependen entre sí), pero matar el proceso servidor del Manager rompe a los 7:
   todos le mandan sus datos a ese servidor, y sin él la conexión falla. El Manager es un punto
   único de falla.

5. **La race del `+=` está a nivel de instrucciones.**
   Reafirmé que `+= 1` no es atómico: son tres pasos (leer, sumar, escribir), y el scheduler puede
   intercalar otro proceso entre el "leer" y el "escribir", con lo que se pierde un incremento.

6. **PID vs TID.**
   El thread principal tiene su TID igual al PID no por ser un "líder", sino porque es el hilo
   original: cuando el proceso arranca es un solo hilo con TID = PID, y recién los threads que crea
   después reciben TIDs nuevos.
