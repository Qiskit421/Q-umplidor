## CI-01 — Salida y errores de varios trabajos en la cola

- **Requisitos (matriz):** MT-09, MT-11, MT-12.
- **Entrada:** `queue echo hola`, `queue python procesos.py` y `queue sleep 2`; después `queue`, `salida 1`, `errores 1`, `salida 2` y `errores 2`.
- **Resultado esperado:** los tres trabajos se ejecutan, cada uno guarda su salida estándar y su salida de error por separado, y `queue` muestra el estado final de cada uno.
- **Resultado obtenido:** `queue` mostró el 1 y el 3 como `SUCCEEDED` con E-Level `0`, y el 2 como `FAILED` con E-Level `-1`. `salida 1` mostró `hola` y `errores 1` mostró `errores: el trabajo [1] no ha escrito nada en la salida de error`. `salida 2` mostró solo las líneas `[INFO]`, por ejemplo `[INFO] Proceso PID 1100 (ls): archivos listados correctamente.`, y `errores 2` mostró solo las líneas `[ERROR]`, por ejemplo `[ERROR] Proceso PID 2100 (cat): el archivo no existe.`

## CI-02 — Cancelar en cola y en ejecución con el límite en 1

- **Requisitos (matriz):** MT-10, MT-12, MT-13.
- **Entrada:** `limite 1`, `queue sleep 30`, `queue sleep 30` y `queue echo tercero`; después `queue`, `queue cancelar 2`, `queue cancelar 1`, `queue` y `salida 3`.
- **Resultado esperado:** solo un trabajo corre a la vez; al cancelar el que espera y el que corre, la cola continúa con el siguiente.
- **Resultado obtenido:** el primer `queue` mostró el 1 como `RUNNING` y el 2 y el 3 como `QUEUED`. `queue cancelar 2` mostró `Trabajo [2] cancelado (estaba en cola)` y `queue cancelar 1` mostró `Trabajo [1] cancelado`. El segundo `queue` mostró el 1 y el 2 como `CANCELED` y el 3 como `SUCCEEDED`; `salida 3` mostró `tercero`.

## CI-03 — Cerrar y reiniciar con trabajos pendientes

- **Requisitos (matriz):** MT-15, MT-16.
- **Entrada:** `limite 1`, `queue sleep 20`, `queue echo pendiente`, `queue sleep 2` y `queue cancelar 3`; se cierra el programa con el trabajo 1 en ejecución. Al volver a abrirlo: `queue`, `salida 2`, `queue sleep 1` y `queue`.
- **Resultado esperado:** al reiniciar se conservan los trabajos de la cola, el que corría queda interrumpido, el que esperaba se ejecuta solo y los IDs continúan sin repetirse.
- **Resultado obtenido:** antes de cerrar, `queue` mostró el 1 como `RUNNING`, el 2 como `QUEUED` y el 3 como `CANCELED`. Al reiniciar, `queue` mostró el 1 como `INTERRUPTED`, el 2 como `SUCCEEDED` y el 3 como `CANCELED`; `salida 2` mostró `pendiente`. El nuevo `queue sleep 1` recibió `ID: [4]`.

## CI-04 — Escalamiento al cancelar un trabajo que no termina

- **Requisitos (matriz):** MT-10, MT-13, MT-14.
- **Entrada:** `politica`, `limite 1`, `queue sleep 60` y `queue echo despues`; después `queue`, `queue cancelar 1`, `queue` y `eventos 1`.
- **Resultado esperado:** `politica` muestra los pasos de escalamiento, el trabajo largo se detiene con esa política al cancelarlo y la cola sigue con el siguiente trabajo.
- **Resultado obtenido:** `politica` mostró `1. SIGTERM al grupo de procesos del trabajo`, `2. Gracia: 2s` y `3. SIGKILL si sigue vivo, y wait() para no dejar zombis`. El primer `queue` mostró el 1 como `RUNNING` y el 2 como `QUEUED`. `queue cancelar 1` mostró `Trabajo [1] cancelado` y el segundo `queue` mostró el 1 como `CANCELED` y el 2 como `SUCCEEDED`. `eventos 1` mostró `JOB_SUBMITTED`, `JOB_STARTED`, `JOB_CANCEL_REQUESTED` y `JOB_CANCELLED ... motivo=cancelado por el usuario`.

## CI-05 — Bitácora de una sesión con trabajos duplicados

- **Requisitos (matriz):** MT-17, MT-19.
- **Entrada:** `queue sleep 3`, `queue sleep 3` y `queue echo hola`; esperar a que terminen y escribir `eventos` y `eventos 2`.
- **Resultado esperado:** se avisa del comando duplicado y la bitácora registra en orden el arranque y el envío, inicio y fin de cada trabajo.
- **Resultado obtenido:** el segundo `queue sleep 3` mostró `aviso: ya hay un trabajo activo con el mismo comando ([1])`. `eventos` mostró `SYSTEM_STARTED` y, por cada trabajo, `JOB_SUBMITTED`, `JOB_STARTED` y `JOB_FINISHED` con `estado=Terminado exit_code=0`; el envío del 2 quedó con `duplicado_de=1`. `eventos 2` mostró solo los tres eventos del trabajo 2.

## CI-06 — Revisar y liberar recursos durante y después de la cola

- **Requisitos (matriz):** MT-20.
- **Entrada:** `recursos`, `queue sleep 4`, `queue echo hola` y `recursos`; esperar a que terminen y escribir `recursos`, `queue clear`, `queue clear`, `recursos` y `queue echo nuevo`.
- **Resultado esperado:** mientras corre un trabajo se ve su proceso vivo; al terminar no quedan procesos, zombis, huérfanos ni archivos abiertos, y `queue clear` deja la cola como nueva.
- **Resultado obtenido:** el primer `recursos` mostró `Trabajos revisados .......... 0 (todavía no se ha lanzado ninguno)`. Con el trabajo 1 corriendo mostró `Procesos hijos vivos ........ 1 (trabajos: [1])`. Al terminar mostró `(terminados: 2)` y todo en `0`. El primer `queue clear` mostró `queue clear: se borraron los trabajos terminados de la cola y sus salidas` y el segundo `queue clear: no hay trabajos terminados en la cola`. Después, `recursos` volvió a mostrar `0 (todavía no se ha lanzado ninguno)` y `queue echo nuevo` recibió `ID: [1]`.

## CI-07 — Cola llena con el límite en 1

- **Requisitos (matriz):** MT-10, MT-13, MT-18.
- **Entrada:** `limite 1` y siete trabajos: `queue sleep 30`, `queue sleep 31`, `queue sleep 32`, `queue sleep 33`, `queue sleep 34`, `queue sleep 35` y `queue sleep 36`; después `queue`, `queue cancelar 3`, `queue sleep 36` y `queue`.
- **Resultado esperado:** con un trabajo corriendo y cinco en espera (la capacidad de la cola), el siguiente se rechaza sin consumir un ID; al cancelar uno que espera, se libera un lugar.
- **Resultado obtenido:** los seis primeros recibieron `ID: [1]` a `ID: [6]`, y el séptimo mostró `queue: cola llena (5/5 en espera), trabajo rechazado. Intenta de nuevo cuando avance la cola.` `queue` mostró el 1 como `RUNNING` y del 2 al 6 como `QUEUED`. Tras `queue cancelar 3`, que mostró `Trabajo [3] cancelado (estaba en cola)`, el nuevo `queue sleep 36` recibió `ID: [7]` y `queue` mostró el 3 como `CANCELED` y el 7 como `QUEUED`.

## CI-08 — Trabajos de afuera y de la cola al mismo tiempo

- **Requisitos (matriz):** MT-09, MT-13.
- **Entrada:** `sleep 30 &` y `queue sleep 30`; después `listar`, `queue`, `estado 1`, `cancelar 1`, `listar`, `queue`, `queue cancelar 1` y `queue`.
- **Resultado esperado:** la cola lleva su propia numeración y sus propios comandos; los comandos del Avance 01 no tocan a los trabajos de la cola ni al revés.
- **Resultado obtenido:** `sleep 30 &` recibió `ID: [1]` y `queue sleep 30` recibió `ID: [1] agregado a la cola`. `listar` mostró solo el `sleep 30 &` como `En ejecución` y `queue` mostró solo el `sleep 30` de la cola como `RUNNING`. `cancelar 1` mostró `Trabajo [1] cancelado`; después `listar` lo mostró como `Cancelado` mientras `queue` seguía mostrando el de la cola como `RUNNING`. `queue cancelar 1` mostró `Trabajo [1] cancelado` y `queue` lo mostró como `CANCELED`.


CTRL + SHIFT + V
