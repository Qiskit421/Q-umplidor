## CR-01 — Encolar un programa que no existe

- **Requisitos (matriz):** MT-09, MT-11.
- **Entrada:** `queue noexiste`; después `queue`, `errores 1` y `salida 1`.
- **Resultado esperado:** el trabajo se acepta, falla sin detener el programa y el error queda en la salida de error.
- **Resultado obtenido:** apareció `ID: [1] agregado a la cola` y `queue` lo mostró como `FAILED` con E-Level `-1`. `errores 1` mostró `'noexiste' is not recognized as an internal or external command, operable program or batch file.` y `salida 1` mostró `salida: el trabajo [1] no ha escrito nada en la salida estándar`.

## CR-02 — Cancelar en la cola sin ID o con un ID inválido

- **Requisitos (matriz):** MT-13.
- **Entrada:** `queue cancelar`, `queue cancelar abc`, `queue cancelar 999` y `queue cancelar 1 2`.
- **Resultado esperado:** indicar el error sin cancelar nada y seguir esperando comandos.
- **Resultado obtenido:** aparecieron `cancelar: falta el ID del trabajo. Uso: cancelar <id>`, `cancelar: el ID debe ser un número`, `cancelar: no existe el trabajo [999] en la cola` y `cancelar: argumentos incorrectos. Uso: cancelar <id>`.

## CR-03 — Cancelar un trabajo de la cola que ya terminó

- **Requisitos (matriz):** MT-13, MT-19.
- **Entrada:** `queue echo hola`; cuando termina, `queue cancelar 1` dos veces y después `queue`.
- **Resultado esperado:** no cambiar el estado del trabajo terminado y responder igual las dos veces.
- **Resultado obtenido:** las dos veces apareció `cancelar: el trabajo [1] ya terminó (Terminado)` y `queue` lo siguió mostrando como `SUCCEEDED`.

## CR-04 — Consultar salida y errores con un ID inválido

- **Requisitos (matriz):** MT-11.
- **Entrada:** `salida 999`, `errores abc`, `salida` y `errores 1 2`.
- **Resultado esperado:** indicar el error y seguir esperando comandos.
- **Resultado obtenido:** aparecieron `salida: no existe el trabajo [999] en la cola`, `errores: el ID debe ser un número`, `salida: falta el ID del trabajo. Uso: salida <id>` y `errores: argumentos incorrectos. Uso: errores <id>`.

## CR-05 — Cambiar el límite con valores inválidos

- **Requisitos (matriz):** MT-10.
- **Entrada:** `limite abc`, `limite 0`, `limite -3`, `limite 2 3` y después `limite`.
- **Resultado esperado:** rechazar el valor sin cambiar el límite actual.
- **Resultado obtenido:** los tres primeros mostraron `limite: el límite debe ser un entero mayor o igual a 1` y el cuarto `limite: argumentos incorrectos. Uso: limite o limite <N>`. Después, `limite` siguió mostrando `Límite de concurrencia: 2 (ocupados ahora: 0)`.

## CR-06 — Consultar la política con argumentos de más

- **Requisitos (matriz):** MT-14.
- **Entrada:** `politica extra`.
- **Resultado esperado:** indicar el uso correcto y seguir esperando comandos.
- **Resultado obtenido:** apareció `politica: no acepta argumentos. Uso: politica`.

## CR-07 — Encolar sin indicar un comando

- **Requisitos (matriz):** MT-09.
- **Entrada:** `queue &` y después `queue`.
- **Resultado esperado:** no agregar nada a la cola y avisar que falta el comando.
- **Resultado obtenido:** `queue &` mostró `queue: debes indicar un comando después de queue` y `queue` mostró `La cola está vacía.`

## CR-08 — Consultar la bitácora con un ID inválido

- **Requisitos (matriz):** MT-17.
- **Entrada:** `eventos abc`, `eventos 999` y `eventos 1 2`.
- **Resultado esperado:** indicar el error o que no hay eventos, sin detener el programa.
- **Resultado obtenido:** aparecieron `eventos: el ID debe ser un número`, `No hay eventos registrados` y `eventos: argumentos incorrectos. Uso: eventos [id]`.

## CR-09 — Revisar recursos con argumentos de más

- **Requisitos (matriz):** MT-20.
- **Entrada:** `recursos extra`.
- **Resultado esperado:** indicar el uso correcto y seguir esperando comandos.
- **Resultado obtenido:** apareció `recursos: no acepta argumentos. Uso: recursos`.

## CR-10 — Limpiar la cola con un trabajo todavía en ejecución

- **Requisitos (matriz):** MT-20.
- **Entrada:** `queue sleep 20` y `queue echo hola`; cuando termina el 2, `queue clear` y después `queue`.
- **Resultado esperado:** borrar solo los trabajos terminados y conservar el que sigue corriendo.
- **Resultado obtenido:** `queue clear` mostró `queue clear: se borraron los trabajos terminados de la cola y sus salidas` y `queue` siguió mostrando el trabajo 1 como `RUNNING`; el 2, que ya había terminado, ya no apareció.
