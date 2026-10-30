## CP-001 — Enviar un trabajo

- **Entrada:** `sleep 5`.
- **Resultado esperado:** aceptar el trabajo y correrlo en primer plano donde no deberia dejar ejecutar otro comando
- **Resultado obtenido** exactamente como el esperado

## CP-002 — Obtener un identificador único

- **Entrada:** escribir `sleep 200 &` 2 veces
- **Resultado esperado:** recibir un identificador diferente para cada trabajo.
- **Resultado obtenido:** aparece `ID: [1]` para el primero e `ID: [2]` para el segundo. La numeración es única dentro de la sesión; vuelve a comenzar al reiniciar.


## CP-003 — Ejecutar el trabajo como proceso separado


- **Entrada:** `sleep 200 &`.
- **Resultado esperado:** debe correr el trabajo permitiendo escribir nuevos comandos 
- **Resultado obtenido:** efectivamente despues de colocar el comando da una salida de ID y permite seguir escribiendo comandos  


## CP-004 — Consultar el estado

- **Entrada:** `estado 1`, con el trabajo `sleep 200 &` activo.
- **Resultado esperado:** mostrar el comando, el estado y el tiempo transcurrido del trabajo con ID 1.
- **Resultado obtenido:** apareció `[1] sleep 200 & -> En ejecución (5s)`.

## CP-005 — Listar trabajos

- **Entrada:** `listar`, después de crear un trabajo con `sleep 200 &`.
- **Resultado esperado:** mostrar los trabajos registrados con su ID, estado, tiempo transcurrido y comando.
- **Resultado obtenido:** se mostró el trabajo con ID 1, estado «En ejecución», tiempo transcurrido de 20 segundos y comando `sleep 200 &`.

## CP-006 — Solicitar la cancelación

- **Entrada:** `cancelar 1`, con el trabajo `sleep 200 &` activo.
- **Resultado esperado:** detener el trabajo con ID 1 y permitir seguir escribiendo comandos.
- **Resultado obtenido:** apareció `Trabajo [1] cancelado`. Al consultar `estado 1`, el trabajo apareció como «Cancelado» y el programa continuó funcionando.

## CP-007 — Obtener el código de salida

- **Entrada:** `codigo 1`, después de que el trabajo con ID 1 termine correctamente.
- **Resultado esperado:** mostrar el código de salida 0.
- **Resultado obtenido:** apareció `codigo: el trabajo [1] terminó con código de salida 0`.

## CP-008 — Manejar un comando inválido

- **Entrada:** `hola`.
- **Resultado esperado:** indicar que no existe dicho programa
- **Resultado obtenido:** apareció `hola: comando no reconocido` y el programa continuó esperando comandos.


## CP-009 — Registrar el arranque y cierre del sistema

- **Entrada:** iniciar `python src/main.py` y salir con Ctrl+C.
- **Resultado esperado:** la bitácora registra `SYSTEM_STARTED` al arrancar y `SYSTEM_STOPPED` al cerrar, en ese orden.
- **Resultado obtenido:** `data/events.jsonl` contiene `SYSTEM_STARTED` (con el número de trabajos previos) seguido de `SYSTEM_STOPPED`.

## CP-010 — Registrar un trabajo en segundo plano

- **Entrada:** `sleep 10 &`, esperar a que termine y consultar con `listar`.
- **Resultado esperado:** la bitácora registra `JOB_STARTED` con el pid y `JOB_FINISHED` con el código de salida, ambos con el mismo ID.
- **Resultado obtenido:** aparecen `JOB_STARTED` (job_id 5, con pid) y `JOB_FINISHED` (job_id 5, estado «Terminado», exit_code 0).

## CP-011 — Ejecutar trabajos en cola uno por uno

- **Entrada:** `queue sleep 3`, `queue sleep 2` y `queue sleep` (sin segundos), luego `queue`.
- **Resultado esperado:** los trabajos se ejecutan en orden, de uno en uno, y cada uno deja `JOB_SUBMITTED`, `JOB_STARTED` y `JOB_FINISHED` en la bitácora.
- **Resultado obtenido:** cada `JOB_STARTED` aparece después del `JOB_FINISHED` del trabajo anterior. `queue` mostró los IDs 6 y 7 con código 0 (3.05 s y 2.05 s). El `queue sleep` sin segundos (ID 8) terminó con «Falló (código 1)», quedó registrado con exit_code 1 y la cola continuó.

## CP-012 — Cancelar un trabajo en ejecución con registro

- **Entrada:** `sleep 30 &` y después `cancelar 9`.
- **Resultado esperado:** el trabajo se detiene y la bitácora registra la petición y la cancelación.
- **Resultado obtenido:** apareció `Trabajo [9] cancelado`. La bitácora muestra `JOB_STARTED`, `JOB_CANCEL_REQUESTED` y `JOB_CANCELLED` (estado «Cancelado», exit_code 1).

## CP-013 — Cancelar un trabajo que está en cola

- **Entrada:** varios `queue sleep 30` seguidos y `cancelar 30` sobre uno que todavía no empezó.
- **Resultado esperado:** el trabajo se cancela sin iniciar ningún proceso, `listar` no falla y la cola continúa con los siguientes.
- **Resultado obtenido:** la bitácora muestra `JOB_SUBMITTED`, `JOB_CANCEL_REQUESTED` y `JOB_CANCELLED` (antes: «En cola») sin `JOB_STARTED`. `listar` lo mostró como «Cancelado» con 0 s, y los trabajos 27 y 28 se ejecutaron después.

## CP-014 — Repetir una cancelación sin efecto

- **Entrada:** `cancelar 23` dos veces y `cancelar 25` sobre un trabajo ya terminado.
- **Resultado esperado:** repetir la cancelación no cambia el trabajo ni genera eventos nuevos.
- **Resultado obtenido:** la primera vez apareció `Trabajo [23] cancelado`. La segunda, `cancelar: el trabajo [23] ya estaba cancelado`, sin eventos nuevos. `cancelar 25` respondió `ya terminó (Terminado)`.

## CP-015 — Rechazar un programa inexistente

- **Entrada:** `ejecutar programa_que_no_existe &`.
- **Resultado esperado:** informar que no se pudo iniciar, no crear ningún trabajo y registrar el rechazo.
- **Resultado obtenido:** apareció `ejecutar: no se pudo iniciar 'programa_que_no_existe': El sistema no puede encontrar el archivo especificado`. La bitácora registró `JOB_REJECTED` sin job_id, con el comando y el motivo, y el programa continuó.

## CP-016 — Interrumpir trabajos al salir

- **Entrada:** `sleep 60 &` y salir de inmediato con Ctrl+C. Se repitió con `queue sleep 30`.
- **Resultado esperado:** el trabajo activo se termina y la bitácora registra una sola interrupción antes del cierre del sistema.
- **Resultado obtenido:** con `sleep 60 &` (ID 10) apareció `JOB_INTERRUPTED` (exit_code 1) seguido de `SYSTEM_STOPPED`. Con `queue sleep 30` (ID 33) hubo un solo `JOB_INTERRUPTED` y ningún `JOB_FINISHED`.

## CP-017 — Cerrar cada trabajo una sola vez

- **Entrada:** varios `queue sleep 2` consecutivos (IDs 14 a 20).
- **Resultado esperado:** cada trabajo se cierra una sola vez, aunque la consola y el hilo de la cola detecten su fin a la vez.
- **Resultado obtenido:** cada trabajo tiene exactamente un `JOB_SUBMITTED`, un `JOB_STARTED` y un `JOB_FINISHED`, todos con su job_id.

## CP-018 — Avisar de un comando duplicado

- **Entrada:** `queue sleep 20` dos veces, `queue sleep    20` (con espacios de más), `sleep 5 &` dos veces y `queue sleep 3`.
- **Resultado esperado:** un comando igual al de un trabajo activo se acepta y muestra un aviso con el ID del trabajo existente. Un comando distinto no avisa. La bitácora registra `duplicado_de`.
- **Resultado obtenido:** los IDs 35 y 36 avisaron `ya hay un trabajo activo con el mismo comando ([34])` y el ID 38 avisó con `([37])`. Los IDs 34, 37 y 39 no mostraron aviso.

## CP-019 — Consultar la bitácora

- **Entrada:** `eventos`, `eventos 11`, `eventos abc` y `eventos 5` (trabajo sin eventos registrados).
- **Resultado esperado:** `eventos` lista los últimos eventos, `eventos <id>` solo los de ese trabajo, y las entradas inválidas muestran un mensaje sin cerrar el programa.
- **Resultado obtenido:** `eventos` mostró los eventos con fecha, número, tipo y datos. `eventos 11` mostró solo `JOB_STARTED` y `JOB_FINISHED` del trabajo 11. `eventos abc` respondió `eventos: el ID debe ser un número` y `eventos 5` respondió `No hay eventos registrados`.

## CP-020 — Pruebas unitarias de la bitácora

- **Entrada:** `python -m unittest discover -s verif/test-cases -v`.
- **Resultado esperado:** pasan las pruebas de orden de eventos, filtro por trabajo, continuidad de la secuencia, línea corrupta y escritura desde varios hilos.
- **Resultado obtenido:** `Ran 5 tests` con resultado `OK`.
