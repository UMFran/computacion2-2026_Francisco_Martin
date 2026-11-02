# Guión de demostración

Para tener abierto durante la corrección.

**La forma rápida es `demo.py`**, que corre los siete momentos en orden y narra cada uno:

```bash
docker compose up -d        # levantar el sistema
python demo.py              # la demo completa
python demo.py --pausa      # frenando entre pasos, para ir explicando
python demo.py 5            # solo un paso (útil si te preguntan por uno)
```

Está en Python y no en un script de shell a propósito: anda igual en Windows, Linux y
dentro del contenedor, y no sufre el manejo de comillas de PowerShell ni el alias de
`curl`.

Lo que sigue es el detalle de cada paso **a mano**, por si te piden hacerlo con `curl` o
te preguntan por un endpoint suelto. Las órdenes están probadas en **PowerShell en
Windows**; al final están las equivalentes en bash.

---

## Antes de empezar: tres cosas que te pueden arruinar la demo

**1. En PowerShell, `curl` NO es curl.** Es un alias de `Invoke-WebRequest`, con otra
sintaxis. Y `curl.exe` con JSON tampoco funciona bien, porque PowerShell se come las
comillas internas:

```powershell
curl.exe -s -X POST localhost:8000/tareas -H 'Content-Type: application/json' -d '{"tipo":"esperar"}'
# {"detail":[{"type":"json_invalid", ... "Expecting property name enclosed in double quotes"}]}
```

**En PowerShell usá `Invoke-RestMethod`** (alias `irm`), que es nativo y devuelve objetos.
Los ejemplos con `curl` del README funcionan tal cual en bash, Linux y dentro del
contenedor.

**2. El timeout por omisión es 30 s.** Una tarea `esperar` de 30 s *compite* con su propio
timeout y lo pierde por milésimas:

```
tarea 46d250da vencio por timeout     # esperar(30) con timeout 30.0 -> fallida
```

Para las demos largas pasá el `timeout` explícito.

**3. Las tareas terminan antes de que termines de tipear.** Con tareas de 5 s, para cuando
escribís el `GET` ya completaron. **Usá tareas de 30-60 s** para tener tiempo.

---

## Levantar el sistema

```powershell
cd TP2
docker compose up --build
```

La terminal queda mostrando los logs — dejala a la vista, porque el log es parte de la
demostración. Abrí una **segunda terminal** para las órdenes.

---

## Paso 1 — El sistema en reposo

```powershell
Invoke-RestMethod http://localhost:8000/estadisticas | ConvertTo-Json
```

```json
{
  "total": 0,
  "por_estado": { "pendiente": 0, "ejecutando": 0, "completada": 0, "fallida": 0, "cancelada": 0 },
  "workers": { "total": 2, "ocupados": 0 },
  "cola": { "encoladas": 0, "maxsize": 100 }
}
```

> **Qué decir:** "Hay 2 workers arrancados y ninguno ocupado. Son dos corrutinas suspendidas
> en `await cola.get()`. No están consumiendo CPU: el event loop está bloqueado en el
> selector del sistema operativo esperando que pase algo."

---

## Paso 2 — El `POST` responde sin esperar a la tarea

```powershell
1..5 | ForEach-Object {
  Invoke-RestMethod -Method Post http://localhost:8000/tareas `
    -ContentType 'application/json' `
    -Body '{"tipo":"esperar","parametros":{"segundos":30},"timeout":120}'
}
```

```
id       estado
--       ------
630e6bbe pendiente
02f4a96a pendiente
...
```

> **Qué decir:** "Cinco tareas de 30 segundos encoladas, y los cinco POST volvieron al
> instante. Medido: 0,021 s en total. Si el endpoint tardara lo que tarda la tarea, el
> diseño estaría mal — la consigna lo dice explícitamente. El POST solo crea la ficha, hace
> `put_nowait` del id y devuelve."

---

## Paso 3 — Ver qué se está ejecutando AHORA

**La respuesta a "¿cómo veo las tareas en ejecución?":**

```powershell
(Invoke-RestMethod http://localhost:8000/tareas?estado=ejecutando).tareas |
  Select-Object id, tipo, estado | Format-Table
```

```
id       tipo    estado
--       ----    ------
065fba24 esperar ejecutando
461acf1b esperar ejecutando
```

**Y el monitor en vivo**, que es lo que conviene dejar corriendo en una tercera terminal:

```powershell
while ($true) {
  $e = Invoke-RestMethod http://localhost:8000/estadisticas
  "{0}  pend={1} ejec={2} compl={3} fall={4} canc={5}  workers {6}/{7}  cola {8}" -f `
    (Get-Date -Format HH:mm:ss), $e.por_estado.pendiente, $e.por_estado.ejecutando,
    $e.por_estado.completada, $e.por_estado.fallida, $e.por_estado.cancelada,
    $e.workers.ocupados, $e.workers.total, $e.cola.encoladas
  Start-Sleep 1
}
```

Así se ve con 5 tareas de 6 s y 2 workers:

```
   0s  pend=3 ejec=2 compl=0   2/2 ocupados, 3 en cola
   6s  pend=1 ejec=2 compl=2   2/2 ocupados, 1 en cola
  12s  pend=0 ejec=1 compl=4   1/2 ocupados, 0 en cola
  20s  pend=0 ejec=0 compl=5   0/2 ocupados, 0 en cola
```

> **Qué decir:** "Nunca hay más de 2 en ejecución porque hay 2 workers. Las otras esperan en
> la `asyncio.Queue`. Y fijate que el tercer escalón tiene un solo worker ocupado: quedaba
> una sola tarea. Esto es la medición 3: el techo no es la cantidad de tareas, es la
> cantidad de workers."

---

## Paso 3b — La línea de tiempo (la mejor evidencia de todas)

Si las tareas ya terminaron, **no perdiste nada**: cada ficha guarda tres marcas de tiempo
(`encolada`, `inicio`, `fin`), así que la historia se reconstruye después. Esta tabla es
mejor que mirar en vivo.

Los tres campos son `time.time()` crudo (epoch Unix, ilegible a ojo), así que hay que
mostrarlos relativos al arranque:

```powershell
$t = (Invoke-RestMethod http://localhost:8000/tareas).tareas
$cero = ($t | Measure-Object -Property encolada -Minimum).Minimum
$t | Select-Object id, estado,
  @{n='encolada';     e={'{0,6:N2}s' -f ($_.encolada - $cero)}},
  @{n='arranco';      e={if($_.inicio){'{0,6:N2}s' -f ($_.inicio - $cero)}else{'-'}}},
  @{n='termino';      e={if($_.fin){'{0,6:N2}s' -f ($_.fin - $cero)}else{'-'}}},
  @{n='esperoEnCola'; e={if($_.inicio){'{0,5:N2}s' -f ($_.inicio - $_.encolada)}else{'-'}}},
  @{n='duro';         e={if($_.inicio -and $_.fin){'{0,5:N2}s' -f ($_.fin - $_.inicio)}else{'-'}}} |
  Format-Table -AutoSize
```

Con 5 tareas de 3 s y 2 workers:

```
id       estado     encolada arranco termino esperoEnCola duro
b67f532a completada   0,00s    0,00s   3,00s  0,00s        3,00s
b874151d completada   0,01s    0,01s   3,02s  0,00s        3,01s
19c98971 completada   0,01s    3,00s   6,02s  2,99s        3,01s
5933dc77 completada   0,01s    3,02s   6,03s  3,01s        3,01s
8b8cd3a5 completada   0,01s    6,02s   9,03s  6,00s        3,01s
```

> **Qué decir:** "Las cinco se encolaron en 0,01 segundos: el POST no espera a nadie.
> Arrancaron de a dos —en 0, 0, 3, 3 y 6— porque hay dos workers, y se ven las tres tandas.
> Cada una duró 3,01 segundos sin importar cuánta congestión había: **el tiempo de
> ejecución no se degrada**. Lo que creció fue la espera en cola, de 0 a 3 a 6 segundos.
> Eso es exactamente lo que mide la medición 3: el sistema no se degrada, se encola."

De esos mismos tres campos salen los promedios de `/estadisticas`: la espera en cola es
`inicio - encolada` y la ejecución es `fin - inicio`.

**Y hay un tercer lugar donde están:** el volcado del apagado,
`estados/estado_<timestamp>.json`, guarda el registro completo con los tres tiempos de cada
tarea. Sirve para analizar una corrida después de que el servidor se apagó.

---

## Paso 4 — Cancelación

```bash
python demo.py 5
```

El script guarda los ids en variables, así que no hay nada que sustituir a mano. Salida
real:

```
Encolo 3 tareas de 60s (hay 2 workers)
  a = a89786f8  ->  ejecutando
  b = ff2d8827  ->  ejecutando
  c = c79e0514  ->  pendiente   <- quedo en la cola

1) DELETE de la que esta EN COLA
   c79e0514  cancelada  pendiente

2) DELETE de la que esta EJECUTANDO
   a89786f8  cancelada  ejecutando

Como quedaron las fichas:
  estaba en cola       cancelada   cancelada mientras esperaba en la cola   nunca arranco
  estaba ejecutando    cancelada   cancelada en ejecucion                   0,96s

El worker sigue vivo: una tarea nueva quedo completada
```

**Por qué el script cancela primero la de la cola:** si se cancela primero una que está
ejecutando, se libera un worker que agarra la de la cola **al instante**, y para cuando
llega el segundo `DELETE` ya pasó a `ejecutando`. Al ensayar me reportó
`se_cancelo_desde: ejecutando` con una duración de 0,00 s. No es un bug —es el sistema
reaccionando— pero arruina la demostración de los dos caminos.

> **Qué decir:** "Son dos caminos distintos. La que estaba en cola no tenía ningún `Task`
> que cancelar: solo marqué la ficha, y el worker la descarta cuando la saque — por eso
> `inicio` quedó en `null`, nunca arrancó. La que estaba ejecutando sí tenía un `Task`
> guardado en el dict `ejecutando`, y le hice `cancel()`: duró 1,01 s de los 60 que pedía.
> El `cancel()` no la mata, le pide al loop que le lance `CancelledError` en su próximo
> `await` — que en este caso era el `asyncio.sleep`."

> **Qué decir (última línea del script):** "Cancelar una tarea no mata al worker. Por eso cada tarea corre en un
> `Task` aparte: si el worker hiciera `await ejecutar_una(tid)` directo, el único Task
> cancelable sería el del worker."

---

## Paso 5 — El event loop bloqueado (el momento fuerte)

```powershell
# SIN executor: bloquea el loop
Invoke-RestMethod -Method Post http://localhost:8000/tareas -ContentType 'application/json' `
  -Body '{"tipo":"hashear","parametros":{"texto":"demo","iteraciones":12000000,"sin_executor":true},"timeout":300}'

# inmediatamente después, cronometrar un GET:
Measure-Command { Invoke-RestMethod http://localhost:8000/tareas } | Select-Object TotalMilliseconds
```

Repetir con `"sin_executor":false`. Medido:

```
sin_executor=True   -> un GET /tareas tardó  4485.6 ms
sin_executor=False  -> un GET /tareas tardó     2.2 ms
```

> **Qué decir:** "Sin executor el `GET` tarda 4,5 segundos: el event loop es un solo hilo y
> la corrutina que calcula no tiene ningún `await` donde ceder el control. No es contención
> de CPU — es que nunca devuelve el control. Con executor, 2 milisegundos. Y lo más
> importante: **el cálculo tarda lo mismo en los dos casos**. El executor no acelera nada,
> solo evita que bloquee a los demás."

---

## Paso 6 — Apagado ordenado

Con tareas en vuelo, en la terminal de los logs: `Ctrl+C`, o desde otra terminal:

```powershell
docker compose stop
Get-ChildItem estados\
```

En el log tienen que aparecer, en este orden:

```
gestor: apagado: dejo de aceptar tareas nuevas
gestor: worker 0 se retira ordenadamente
gestor: worker 1 se retira ordenadamente
gestor: los 2 workers salieron ordenadamente
gestor: estado volcado en estados\estado_20261102_183844.json
```

Y al volver a levantarlo:

```
gestor: volcado previo encontrado: estados\estado_20261102_183844.json (N tareas).
        No se restaura el estado.
```

> **Qué decir:** "El `SIGTERM` lo atrapa uvicorn, que corre el apagado del `lifespan`. Meto
> un centinela por worker: cada uno termina lo que tiene entre manos y recién ahí se
> retira, así ninguna tarea queda a medias. Si se agota el límite de 10 segundos, corto por
> cancelación. El `stop_grace_period: 20s` del compose existe porque Docker manda `SIGKILL`
> a los 10 segundos por omisión y el volcado no llegaría a escribirse."

---

## Las órdenes equivalentes en bash / Linux / dentro del contenedor

```bash
curl -s localhost:8000/estadisticas

curl -s -X POST localhost:8000/tareas -H 'Content-Type: application/json' \
  -d '{"tipo":"esperar","parametros":{"segundos":30},"timeout":120}'

curl -s 'localhost:8000/tareas?estado=ejecutando'

curl -s -X DELETE localhost:8000/tareas/<id>

watch -n1 'curl -s localhost:8000/estadisticas'
```

---

## Si algo sale mal en vivo

| Síntoma | Causa probable |
|---|---|
| `json_invalid` al hacer POST | Estás usando `curl`/`curl.exe` en PowerShell. Usá `Invoke-RestMethod` |
| La tarea quedó `fallida` sin motivo claro | Timeout por omisión de 30 s. Pasá `"timeout": 120` |
| No veo ninguna tarea `ejecutando` | Ya terminaron. Usá tareas de 30-60 s |
| `se_cancelo_desde: ejecutando` cuando esperabas `pendiente` | Un worker la agarró entre tus dos órdenes. Cancelá primero la encolada |
| El `POST` devuelve 503 | La cola está llena (100) o el servidor se está apagando |
| Las tareas ya terminaron y no vi nada | Usá la línea de tiempo del paso 3b: los tiempos quedan en la ficha |
| `docker compose stop && ls` falla | PowerShell no tiene `&&`. Usá `;` |
| `{"detail":"no existe la tarea"}` | Copiaste un `<id-de-algo>` literal. Los `<...>` son marcadores: usá el script, que guarda los ids en variables |
| Me equivoco tipeando en vivo | Usá `python demo.py <n>` para el paso que te pidan |
