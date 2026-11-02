# Dudas — TP2

Preguntas que me quedaron mientras desarrollaba. Algunas las resolví y dejo anotado cómo;
otras siguen abiertas y las traigo a consulta.

---

## Resueltas durante el desarrollo

### ¿Cómo distingo una cancelación de tarea de una cancelación de worker?

**El problema:** las dos llegan al worker como el mismo `asyncio.CancelledError`, pero
tiene que reaccionar distinto — seguir vivo si cancelaron la tarea, irse si lo cancelaron
a él durante el apagado.

Probé `tarea.cancelled()` y no sirve: cuando cancelan al worker, el `await` de la tarea
interna también se cancela, así que da `True` en los dos casos.

**Lo que hice:** un set `cancelados_por_delete` con los ids que pidió cancelar el `DELETE`.
Funciona, pero se siente artesanal.

**Lo que no terminé de entender:** leí que en Python 3.11+ existe
`asyncio.current_task().cancelling()`, que devuelve cuántas veces le pidieron cancelación
a *esta* tarea, y que sería la forma "oficial" de distinguirlo. ¿Es realmente la forma
canónica? ¿Vale la pena contra la legibilidad del set?

### ¿Por qué mi hash tarda la mitad que en el ejemplo de la clase?

`clase21/executor.py` asume que 3.000.000 de iteraciones son ~5 s, y en mi máquina
2.000.000 tardaban 1,1 s. No era un error: la máquina es más rápida. Tuve que calibrar a
12.000.000 para que la medición 2 mostrara bien el bloqueo.

**Lo aprendido:** una medición con una constante fija no es portable. Debí haber calibrado
desde el principio en vez de confiar en el número del ejemplo — por eso el script de la
medición 2 ahora calibra solo antes de medir.

### ¿Por qué el volcado no se escribía al parar el contenedor?

Porque `docker stop` manda `SIGTERM` y espera **10 s** por omisión antes de `SIGKILL`, que
no se puede atrapar — y mi `ESPERA_APAGADO` también era 10 s, así que llegaban juntos.
Se arregló con `stop_grace_period: 20s` en el compose.

---

## Abiertas

### 1. ¿Está bien no instalar un handler de señal propio?

La consigna sugiere `loop.add_signal_handler()`. Yo no lo usé porque **uvicorn ya atrapa
`SIGTERM` y `SIGINT`**, y si instalo el mío lo sobreescribo (el handler es uno por señal,
no una cadena) y el servidor no se apagaría nunca. Puse el apagado en el `lifespan`, que es
lo que uvicorn corre al recibir la señal.

Creo que es lo correcto, pero me quedó la duda de si la cátedra espera ver el
`add_signal_handler` explícito como evidencia de que entendí el tema. **¿Hay alguna forma
de encadenar handlers en asyncio**, o la única opción es o uno o el otro?

### 2. ¿Se puede hacer cancelable una tarea CPU-bound?

Medí que cancelar un `hashear` que ya arrancó en un proceso hijo no lo interrumpe: el
proceso sigue quemando un núcleo, y dos hashes nuevos pasaron de 5,1 s a 16,2 s por culpa
del zombi.

Se me ocurren dos salidas y ninguna me convence:

- **Partir el cálculo en bloques** con un `await asyncio.sleep(0)` entre ellos. Da puntos de
  cancelación, pero entonces el cálculo vuelve a correr *en el loop* y pierdo todo el
  sentido del executor. ¿O se puede hacer por bloques *dentro* del executor, devolviendo el
  control a cada tanto?
- **Matar el proceso hijo.** `ProcessPoolExecutor` no expone los PID de sus workers, y
  `shutdown(cancel_futures=True)` se lleva puestas también las otras tareas en vuelo.
  ¿`multiprocessing.Process` a mano sería la respuesta, perdiendo la comodidad del pool?

**¿Cuál es la práctica real en un sistema de verdad?** Mi sospecha es que se acepta la
limitación y se acotan los trabajos para que sean cortos, pero no lo sé.

### 3. ¿Cuántos workers conviene poner?

En la medición 3 subir de 2 a 8 workers mejoró 4x el trabajo I/O sin ningún costo visible.
La pregunta obvia: ¿por qué no 1000? Entiendo que en algún lado está el techo (memoria de
cada Task, descriptores de archivo, el costo de que el loop recorra más tareas listas),
pero no llegué a encontrarlo empíricamente — a 64 tareas todavía escalaba limpio.

**¿Hay una regla de dedo**, o es siempre "medí en tu caso"?

### 4. El semáforo de `descargar` es por tarea, no global

Cada tarea `descargar` tiene su propio `Semaphore(10)`. Si hay 10 tareas `descargar`
corriendo, puede haber 100 conexiones abiertas entre todas — el límite global no existe.

Para hacerlo global tendría que crear el semáforo en el `lifespan` y pasárselo a la tarea,
igual que el `pool`. **¿Es lo que se espera**, o un límite por tarea alcanza en la práctica?

### 5. ¿El registro en memoria debería tener expiración?

Cada tarea queda guardada para siempre con su resultado. Lo declaré como limitación, pero
no sé cuál sería la solución estándar: ¿un TTL por ficha? ¿un tope de N tareas con
descarte de las más viejas? ¿Y qué pasa si alguien consulta un `id` que ya se expiró —
`404` o `410 Gone`?

---

## Para repasar antes del oral

Las seis preguntas que publica la consigna, con el estado de cada una:

| Pregunta | Estado |
|---|---|
| ¿Dónde podría bloquear el event loop? | ✅ `tareas.py`, `hashear_bloqueante` llamado directo — medido en la medición 2 |
| ¿Qué pasa si cancelo a mitad de una descarga? | ✅ El `async with` del `AsyncClient` cierra las conexiones por el `__aexit__` |
| ¿Por qué el pool no necesita `Lock`? | ⚠️ Lo sé decir, pero quiero poder mostrar también el caso en que *sí* haría falta |
| ¿Qué se rompe con 10.000 tareas? | ✅ La cola: 100 entran, el resto `503`. Medido en la medición 3-D |
| `gather` vs `for` con `await` | ✅ 0,60 s contra 10,27 s. Medición 1 |
| `time.sleep()` vs `asyncio.sleep()` | ✅ Duerme el hilo del loop; además lo hace incancelable |
