## CR-01 — Encolar un programa que no existe

- **Requisitos (matriz):** MT-09, MT-11.
- **Entrada:** `queue noexiste`; después `errores 1` y `salida 1`.
- **Resultado esperado:** el trabajo se acepta, falla sin detener el programa y el error queda en la salida de error.
- **Resultado obtenido:** apareció `ID: [1] agregado a la cola`; `queue` lo mostró como `FAILED`. `errores 1` mostró `'noexiste' is not recognized as an internal or external command, operable program or batch file.` y `salida 1` mostró `salida: el trabajo [1] no ha escrito nada en la salida estándar`.

## CR-02 — Cancelar en la cola sin ID o con un ID inválido

- **Requisitos (matriz):** MT-13.
- **Entrada:** `queue cancelar`, `queue cancelar abc` y `queue cancelar 999`.
- **Resultado esperado:** indicar el error sin cancelar nada y seguir esperando comandos.
- **Resultado obtenido:** aparecieron `cancelar: falta el ID del trabajo. Uso: cancelar <id>`, `cancelar: el ID debe ser un número` y `cancelar: no existe el trabajo [999]`.

## CR-03 — Cancelar un trabajo de la cola que ya terminó

- **Requisitos (matriz):** MT-13, MT-19.
- **Entrada:** `queue echo hola`; cuando termina, `queue cancelar 1` dos veces.
- **Resultado esperado:** no cambiar el estado del trabajo terminado y responder igual las dos veces.
- **Resultado obtenido:** las dos veces apareció `cancelar: el trabajo [1] ya terminó (Terminado)` y `queue` lo siguió mostrando como `SUCCEEDED`.

## CR-04 — Consultar salida y errores con un ID inválido

- **Requisitos (matriz):** MT-11.
- **Entrada:** `salida 999`, `errores abc` y `salida`.
- **Resultado esperado:** indicar el error y seguir esperando comandos.
- **Resultado obtenido:** aparecieron `salida: no existe el trabajo [999]`, `errores: el ID debe ser un número` y `salida: falta el ID del trabajo. Uso: salida <id>`.

## CR-05 — Cambiar el límite con valores inválidos

- **Requisitos (matriz):** MT-10.
- **Entrada:** `limite abc`, `limite 0`, `limite -3` y `limite 2 3`.
- **Resultado esperado:** rechazar el valor sin cambiar el límite actual.
- **Resultado obtenido:** los tres primeros mostraron `limite: el límite debe ser un entero mayor o igual a 1` y el último `limite: argumentos incorrectos. Uso: limite o limite <N>`. Después, `limite` siguió mostrando `Límite de concurrencia: 2 (ocupados ahora: 0)`.

## CR-06 — Consultar la política con argumentos de más

- **Requisitos (matriz):** MT-14.
- **Entrada:** `politica extra`.
- **Resultado esperado:** indicar el uso correcto y seguir esperando comandos.
- **Resultado obtenido:** apareció `politica: no acepta argumentos. Uso: politica`.

## CR-07 — Iniciar con una capacidad de cola inválida

- **Requisitos (matriz):** MT-18.
- **Entrada:** iniciar el programa con `Q_CAPACIDAD_COLA=abc` y después con `Q_CAPACIDAD_COLA=0`.
- **Resultado esperado:** no arrancar con una capacidad inválida e indicar el motivo.
- **Resultado obtenido:** apareció `Q_CAPACIDAD_COLA debe ser un entero mayor o igual a 1 (se recibió 'abc')` y, en el segundo caso, `(se recibió '0')`. El programa no se inició.

## CR-08 — Consultar la bitácora con un ID inválido

- **Requisitos (matriz):** MT-17.
- **Entrada:** `eventos abc` y `eventos 999`.
- **Resultado esperado:** indicar el error o que no hay eventos, sin detener el programa.
- **Resultado obtenido:** aparecieron `eventos: el ID debe ser un número` y `No hay eventos registrados`.

## CR-09 — Revisar recursos con argumentos de más

- **Requisitos (matriz):** MT-20.
- **Entrada:** `recursos extra`.
- **Resultado esperado:** indicar el uso correcto y seguir esperando comandos.
- **Resultado obtenido:** apareció `recursos: no acepta argumentos. Uso: recursos`.
