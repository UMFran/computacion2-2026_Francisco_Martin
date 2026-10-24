# Clase 11: Sincronización — Respuestas

Los archivos `ejercicio1.py` a `ejercicio7.py` son el código. Acá van las
preguntas escritas.

---

## Ejercicio 1: race condition

El test que da la consigna dice "saldo esperado: 1000", pero con depósitos y
retiros al azar el saldo final **no** es 1000 ni siquiera con el lock: depende
de cuántos depósitos y cuántos retiros exitosos salieron sorteados. Para poder
verificar algo hay que contar las operaciones que de verdad ocurrieron y
comparar contra `1000 + 10*(depósitos - retiros)`.

Corrida real:

```
--- CuentaInsegura ---
  491 depositos y 509 retiros exitosos
  Saldo esperado: 820
  Saldo obtenido: 920
  ERROR: se perdieron 100 por actualizaciones pisadas

--- CuentaSegura ---
  504 depositos y 496 retiros exitosos
  Saldo esperado: 1080
  Saldo obtenido: 1080
  OK: cuadra
```

La insegura perdió 10 operaciones. El `time.sleep(0.001)` entre leer `self.saldo`
y escribirlo agranda la ventana donde otro hilo lee el mismo valor viejo: las dos
escrituras pisan el mismo dato y una de las dos se pierde.

---

## Ejercicio 5: Readers-Writers (obligatorio)

- [x] Permitir múltiples lectores simultáneos
- [x] Bloquear escritores mientras hay lectores
- [x] Bloquear lectores mientras hay escritor
- [x] Solo permitir un escritor a la vez
- [x] Usar Condition para la espera
- [x] Implementar context managers para uso fácil
- [x] No causar deadlocks ni starvation evidente

Las dos `Condition` comparten el mismo `Lock` (`Condition(self.lock)`), que es lo
que permite que `acquire_read` y `acquire_write` revisen los contadores sin
pisarse. Los `while` en vez de `if` son necesarios: `wait()` puede despertar y
encontrarse con que otro hilo ya se adelantó, así que hay que volver a chequear
la condición.

Esta implementación favorece a los lectores: `release_write` hace
`can_read.notify_all()` y un solo `can_write.notify()`, así que con lectores
llegando todo el tiempo un escritor puede esperar mucho. No es deadlock, es
starvation, y para evitarla habría que llevar un contador de escritores en
espera y bloquear lectores nuevos cuando hay alguno.

---

## Ejercicio 7: Filósofos comensales

### 1. ¿Por qué la `Barrier` convierte un deadlock esporádico en uno seguro?

Porque fuerza exactamente el entrelazado que produce el deadlock. La espera
circular necesita que los cinco filósofos tengan su tenedor izquierdo **al mismo
tiempo**; con `sleep` al azar esa coincidencia pasa rara vez. La barrera no
agrega ningún bug: el `with tenedores[izq]` seguido de `with tenedores[der]` ya
era incorrecto. Lo único que hace es garantizar el orden de ejecución que
convierte un bug probabilístico en uno determinista.

Esa es la razón de fondo por la que los deadlocks son difíciles de testear: el
código defectuoso pasa los tests cientos de veces y falla en producción, donde la
carga y la latencia cambian el entrelazado.

Verificado: `python3 ejercicio7.py --a` se cuelga siempre (lo corrí con
`timeout 6` y salió con código 124, o sea que seguía trabado).

Las cuatro condiciones de Coffman se cumplen las cuatro:

| Condición | Cómo se cumple acá |
|---|---|
| Exclusión mutua | Un tenedor es un `Lock`: lo tiene uno solo |
| Retención y espera | Cada filósofo retiene el izquierdo mientras espera el derecho |
| Sin desalojo | Nadie le puede sacar un tenedor a otro; se suelta voluntariamente |
| Espera circular | 0 espera a 1, 1 a 2, ... y 4 espera a 0 |

### 2. ¿Cuál de las otras tres condiciones rompe la solución del semáforo?

**Retención y espera**, en los hechos. El `Semaphore(N-1)` garantiza que a lo
sumo 4 filósofos compitan por 5 tenedores, así que siempre hay al menos uno que
consigue los dos y termina soltándolos. Dicho en términos del ciclo: con sólo 4
participantes es imposible cerrar la cadena circular de 5, porque siempre queda
un tenedor sin reclamar.

Por eso alcanza con N-1 y no hace falta bajar más: el ciclo necesita los cinco.

La jerarquía de la parte B rompe la otra: ordenando los índices no puede existir
espera circular, porque un ciclo requeriría que alguien pidiera un índice menor
teniendo uno mayor, y eso no pasa nunca.

### 3. ¿Es deadlock, starvation o ninguna de las dos?

**Ninguna de las dos**, tal como está medido. Los dos programas completan las 3
comidas por filósofo, así que nadie se queda sin comer: no hay deadlock (nadie
queda trabado para siempre) ni starvation (nadie es postergado indefinidamente).

Lo que sí hay es **reparto desparejo**: la espera acumulada varía bastante entre
filósofos. En una corrida:

```
--- Parte B: jerarquía de recursos ---
  tiempo total: 0.315s
  comidas por filósofo: [3, 3, 3, 3, 3]
  espera acumulada por filósofo: ['0.187', '0.168', '0.115', '0.119', '0.205']

--- Parte C: semáforo de N-1 ---
  tiempo total: 0.248s
  comidas por filósofo: [3, 3, 3, 3, 3]
  espera acumulada por filósofo: ['0.101', '0.135', '0.080', '0.076', '0.187']
```

Eso es falta de *fairness*, que es un problema de rendimiento, no de corrección.
La forma de medirlo es la de arriba: acumular cuánto esperó cada filósofo entre
que quiso comer y que lo logró, y mirar la dispersión. Si se quisiera medir
starvation de verdad habría que dejar correr el programa indefinidamente y ver si
algún filósofo deja de progresar.

Un detalle de la jerarquía: el filósofo 4 es el asimétrico. Para todos los demás
el de menor índice es el izquierdo, pero para el 4 (izq=4, der=0) el menor es el
derecho, así que toma primero el derecho. Esa asimetría es justamente lo que
rompe el ciclo.
