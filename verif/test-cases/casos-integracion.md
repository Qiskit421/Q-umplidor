## CI-01 — Salida y errores de varios trabajos en la cola

- **Requisitos (matriz):** MT-09, MT-11, MT-12.
- **Entrada:** `queue echo hola`, `queue python noexiste.py` y `queue sleep 2`; después `queue`, `salida 1`, `errores 1`, `salida 2` y `errores 2`.
- **Resultado esperado:** los tres trabajos se ejecutan en orden, cada uno guarda su salida estándar y su salida de error por separado, y `queue` muestra el estado final de cada uno.
- **Resultado obtenido:** `queue` mostró `SUCCEEDED` para el 1 y el 3 con E-Level `0`, y `FAILED` para el 2. `salida 1` mostró `hola` y `errores 1` mostró `errores: el trabajo [1] no ha escrito nada en la salida de error`. `salida 2` mostró `salida: el trabajo [2] no ha escrito nada en la salida estándar` y `errores 2` mostró `python: can't open file '...noexiste.py': [Errno 2] No such file or directory`.

## CI-02 — Cancelar en cola y en ejecución con el límite en 1

- **Requisitos (matriz):** MT-10, MT-12, MT-13.
- **Entrada:** `limite 1`, `queue sleep 30`, `queue sleep 30` y `queue echo tercero`; después `queue`, `queue cancelar 2`, `queue cancelar 1`, `queue` y `salida 3`.
- **Resultado esperado:** solo un trabajo corre a la vez; al cancelar el que espera y el que corre, la cola continúa con el siguiente.
- **Resultado obtenido:** el primer `queue` mostró el 1 como `RUNNING` y el 2 y el 3 como `QUEUED`. `queue cancelar 2` mostró `Trabajo [2] cancelado (estaba en cola, no llegó a ejecutarse)` y `queue cancelar 1` mostró `Trabajo [1] cancelado`. El segundo `queue` mostró el 1 y el 2 como `CANCELED` y el 3 como `SUCCEEDED`; `salida 3` mostró `tercero`.

## CI-03 — Cerrar y reiniciar con trabajos pendientes

- **Requisitos (matriz):** MT-15, MT-16.
- **Entrada:** `limite 1`, `queue sleep 20`, `queue echo pendiente`, `queue sleep 2` y `queue cancelar 3`; se cierra el programa con el trabajo 1 en ejecución. Al volver a abrirlo: `queue`, `salida 2`, `queue sleep 1` y `queue`.
- **Resultado esperado:** al reiniciar se conservan los trabajos, el que corría queda interrumpido, el que esperaba se ejecuta solo y los IDs continúan sin repetirse.
- **Resultado obtenido:** antes de cerrar, `queue` mostró el 1 como `RUNNING`, el 2 como `QUEUED` y el 3 como `CANCELED`. Al reiniciar, `queue` mostró el 1 como `INTERRUPTED`, el 2 como `SUCCEEDED` y el 3 como `CANCELED`; `salida 2` mostró `pendiente`. El nuevo `queue sleep 1` recibió `ID: [4]`.

## CI-04 — Trabajo que no termina dentro de la cola

- **Requisitos (matriz):** MT-10, MT-14.
- **Entrada:** iniciar con `Q_TIEMPO_MAXIMO=4`; `limite 1`, `queue sleep 3`, `queue sleep 60` y `queue echo despues`; esperar unos segundos y escribir `queue`.
- **Resultado esperado:** el trabajo que supera el tiempo máximo se detiene con la política de escalamiento y la cola sigue con el siguiente trabajo.
- **Resultado obtenido:** apareció `[aviso] Trabajo [2] superó el tiempo máximo y se detuvo (terminó con SIGTERM)`. `queue` mostró el 1 como `SUCCEEDED` (`3.06s ejecución`), el 2 como `FAILED` (`4.40s ejecución`) y el 3 como `SUCCEEDED`.

## CI-05 — Bitácora de una sesión con trabajos duplicados

- **Requisitos (matriz):** MT-17, MT-19.
- **Entrada:** `queue sleep 3`, `queue sleep 3` y `queue echo hola`; esperar a que terminen y escribir `eventos` y `eventos 2`.
- **Resultado esperado:** se avisa del comando duplicado y la bitácora registra en orden el arranque y el envío, inicio y fin de cada trabajo.
- **Resultado obtenido:** el segundo `queue sleep 3` mostró `aviso: ya hay un trabajo activo con el mismo comando ([1])`. `eventos` mostró `SYSTEM_STARTED` y, por cada trabajo, `JOB_SUBMITTED`, `JOB_STARTED` y `JOB_FINISHED` con `estado=Terminado exit_code=0`; el envío del 2 quedó con `duplicado_de=1`. `eventos 2` mostró solo los tres eventos del trabajo 2.

## CI-06 — Revisar y liberar recursos durante y después de la cola

- **Requisitos (matriz):** MT-20.
- **Entrada:** `recursos`, `queue sleep 4`, `queue echo hola` y `recursos`; esperar a que terminen y escribir `recursos`, `queue clear`, `queue clear` y `recursos`.
- **Resultado esperado:** mientras corre un trabajo se ve su proceso vivo; al terminar no quedan procesos, zombis, huérfanos ni archivos abiertos, y `queue clear` borra las salidas una sola vez.
- **Resultado obtenido:** el primer `recursos` mostró `Trabajos revisados .......... 0 (todavía no se ha lanzado ninguno)`. Con el trabajo 1 corriendo mostró `Procesos hijos vivos ........ 1 (trabajos: [1])`. Al terminar mostró `(terminados: 2)` y todo en `0`. El primer `queue clear` mostró `se borraron 4 archivos de salida de trabajos terminados` y el segundo `no hay archivos de salida de trabajos terminados`.

## CI-07 — Cola llena con el límite en 1

- **Requisitos (matriz):** MT-10, MT-13, MT-18.
- **Entrada:** iniciar con `Q_CAPACIDAD_COLA=2`; `limite 1` y cuatro veces `queue sleep 30`; después `queue`, `queue cancelar 2`, `queue sleep 30` y `queue`.
- **Resultado esperado:** con un trabajo corriendo y dos en espera, el siguiente se rechaza sin consumir un ID; al cancelar uno que espera, se libera un lugar.
- **Resultado obtenido:** los tres primeros recibieron `ID: [1]`, `ID: [2]` e `ID: [3]`, y el cuarto mostró `queue: cola llena (2/2 en espera), trabajo rechazado. Intenta de nuevo cuando avance la cola.` Tras `queue cancelar 2`, el nuevo `queue sleep 30` recibió `ID: [4]` y `queue` mostró el 1 como `RUNNING`, el 2 como `CANCELED` y el 3 y el 4 como `QUEUED`.
