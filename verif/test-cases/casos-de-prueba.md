

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


---

# Avance 02 — Concurrencia, estados, escalamiento y recuperación (integración y robustez)

**Responsable:** Ruy Valle.

Todos los casos los ejecuta y verifica automáticamente `verif/scripts/prueba_avance02_ruy.py`. El script corre una copia de `src/` en una carpeta temporal, así que no toca `data/`. Cada caso deja su evidencia en `verif/results/<caso>-<fecha>/`:
- `entorno.txt`
- `salida_consola.txt`
- `verificacion.txt` (cada comprobación con PASS/FAIL)
- `trabajos.json`

```bash
python3 verif/scripts/prueba_avance02_ruy.py            # todos
python3 verif/scripts/prueba_avance02_ruy.py TC-025     # uno
```

## TC-020 — Límite de concurrencia (RF-05)

- **Configuración:** `Q_LIMITE_CONCURRENCIA=2`
- **Entrada:** 3 × `sleep 2 &`, `queue sleep 2`, `ejecutar echo hola &`; luego `limite 3`, `limite 0`, `limite x`
- **Resultado esperado:**
  - Nunca hay más de 2 procesos de trabajos a la vez; el script los cuenta con `ps` cada 50 ms.
  - El tercer `&` pasa a `QUEUED`.
  - Los encolados arrancan en orden de llegada cuando se libera un lugar.
  - Los 5 terminan `SUCCEEDED`.
  - `limite 3` cambia el límite en caliente.
  - `limite 0` y `limite x` se rechazan.

## TC-021 — Estados y tiempos coherentes (RF-06)

- **Configuración:** `Q_LIMITE_CONCURRENCIA=1`
- **Entrada:** `sleep 2 &` (éxito), `ejecutar bash -c 'exit 3' &` (falla), `queue sleep 30` (se cancela en cola)
- **Resultado esperado:**
  - Se observan `RUNNING` y `QUEUED`.
  - Al final: `SUCCEEDED`, `FAILED` (`codigo` = 3) y `CANCELED` sin hora de inicio.
  - Para todos: envío ≤ inicio ≤ fin.
  - El trabajo que esperó registra espera ≥ 1 s.
  - Ningún trabajo queda en un estado no final.
  - `estado <id>` muestra Enviado, Inicio, Fin, Espera y Ejecución.

## TC-022 — Escalamiento SIGTERM → SIGKILL sin huérfanos (RF-30, RF-10)

- **Configuración:** `Q_GRACIA_SIGTERM=1`
- **Entrada:**
  - `sleep 300 &` (obediente)
  - un programa que ignora SIGTERM (terco)
  - `queue sleep 77; echo fin`
  - `ejecutar bash -c 'sleep 88; echo x' &`
  - Después se cancelan los cuatro.
- **Resultado esperado:**
  - El obediente termina con SIGTERM (`codigo` 143).
  - El terco espera la gracia (~1 s) y se fuerza con SIGKILL (`codigo` 137).
  - Los 4 quedan `CANCELED`.
  - Ningún proceso de los trabajos (incluidos los `sleep` hijos de `bash`) sigue vivo.
  - `motivo_fin` y `senal_final` quedan guardados.

## TC-023 — Tiempo máximo por trabajo (RF-30)

- **Configuración:** `Q_TIEMPO_MAXIMO=2`, `Q_GRACIA_SIGTERM=1`
- **Entrada:** el programa terco y un `sleep 1 &`.
- **Resultado esperado:**
  - El terco se detiene solo, entre 2 y 4.5 s, con SIGKILL, y queda `FAILED (tiempo máximo excedido)`.
  - El `sleep 1` termina normal.
  - Se avisa en la consola.

## TC-024 — Proceso hijo terminado desde fuera (robustez)

- **Entrada:** `ejecutar sleep 300 &` y `queue sleep 301`. Desde otra terminal, `kill -KILL` al primero y `kill -TERM` al segundo.
- **Resultado esperado:**
  - No quedan zombis, aunque nadie haya consultado los trabajos.
  - Ambos quedan `FAILED` con `codigo` 137 y 143.
  - No se reportan como `CANCELED`, porque nadie pidió cancelar.

## TC-025 — Caída abrupta (kill -9) y recuperación (RF-12, RF-13, RNF-10)

- **Configuración:** `Q_LIMITE_CONCURRENCIA=3`, `Q_GRACIA_SIGTERM=1`
- **Entrada:**
  - 3 trabajos corriendo (uno ignora SIGTERM) y 1 en cola.
  - `kill -9` a Q-umplidor; luego se vuelve a arrancar.
- **Resultado esperado:**
  - Tras la caída, los procesos de los trabajos siguen vivos con padre 1. Esto confirma que el escenario es real.
  - Al reiniciar, Q-umplidor los reconoce por su huella (pid + inicio del proceso + `boot_id`) y los detiene con el escalamiento: el terco con SIGKILL.
  - Ninguno sigue vivo.
  - Los 3 quedan `INTERRUPTED` con el motivo "recuperación: proceso huérfano detenido".
  - El de la cola se retoma y termina.
  - Los ID no se repiten.
- **Regresión de:** [INC-002](../../docs/incidents/INC-002.md).

## TC-026 — Cierre por SIGTERM / SIGHUP sin huérfanos (RF-13)

- **Entrada:** 2 trabajos corriendo (uno terco); se envía `kill -TERM` y, en otra corrida, `kill -HUP` a Q-umplidor. SIGHUP es la señal que llega al cerrar la terminal.
- **Resultado esperado:**
  - Q-umplidor sale con código 0.
  - Ningún proceso de los trabajos sigue vivo.
  - Ambos quedan `INTERRUPTED` con el motivo "cierre de Q-umplidor".
- **Regresión de:** [INC-002](../../docs/incidents/INC-002.md).

## TC-027 — Saturación de la cola con el límite lleno (RF-25, RF-05, RNF-29)

- **Configuración:** `Q_LIMITE_CONCURRENCIA=1`, `Q_CAPACIDAD_COLA=2`
- **Entrada:** `sleep 30 &` ×2, `queue sleep 30` ×2 y `sleep 30 &`
- **Resultado esperado:**
  - Los dos envíos que no caben se rechazan con "cola llena (2/2 en espera)".
  - No se anuncia "se envía a la cola" antes del rechazo.
  - Los rechazados no se registran ni consumen ID.
