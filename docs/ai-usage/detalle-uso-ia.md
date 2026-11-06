# 📄 Detalle del uso de IA

Detalle de cada entrada de [RegistroIA.md](RegistroIA.md). El ID de cada sección es el mismo que el de la tabla.

Cada entrada responde seis cosas, como pide el estándar del cliente (doc. 04): **objetivo**, **resultado recibido**, **revisión realizada**, **cambios aplicados**, **prueba agregada** y **aprendizaje**.

---

## IA-001 — Plantilla del registro de IA

- **Integrante:** Marlene Sandoval
- **Objetivo:** tener un documento para registrar el uso de IA.
- **Resultado recibido:** plantillas para `RegistroIA.md` y `detalle-uso-ia.md`.
- **Revisión realizada:** se revisaron los campos de la tabla.
- **Cambios aplicados:** se quitaron algunos campos para dejar solo la información más relevante.
- **Prueba agregada:** no aplica (documento).
- **Aprendizaje:**

## IA-002 — `sleep N &`, `listar` y `codigo`

- **Integrante:** Ruy Valle
- **Objetivo:** implementar RF-04, RF-09 y RF-07 sobre `src/main.py`.
- **Resultado recibido:** bloque `sleep N &` con `subprocess.Popen`, comando `listar` y comando `codigo <id>`.
- **Revisión realizada:** prueba manual interactiva.
- **Cambios aplicados:** se ajustó el manejo de errores (`ValueError`) antes de integrarlo.
- **Prueba agregada:**
- **Aprendizaje:**

## IA-003 — Script de verificación del Avance 1

- **Integrante:** Ruy Valle
- **Objetivo:** script de verificación funcional y evidencia del Avance 1.
- **Resultado recibido:** script con 8 casos.
- **Revisión realizada:** se ejecutó el script.
- **Cambios aplicados:** se corrigió un caso que fallaba (faltaba un `listar` final) hasta lograr 8/8.
- **Prueba agregada:** `verif/scripts/test_avance1_completo.py`
- **Aprendizaje:**

## IA-004 — Ejemplo de envío de trabajo e ID

- **Integrante:** Misael
- **Objetivo:** ver cómo se muestra normalmente en terminal el envío de un trabajo y su ID.
- **Resultado recibido:** ejemplo y explicación de cuándo se muestra el ID.
- **Revisión realizada:**
- **Cambios aplicados:**
- **Prueba agregada:**
- **Aprendizaje:**

## IA-005 — Ejemplos de casos de prueba y matriz

- **Integrante:** Misael
- **Objetivo:** ejemplos de casos de prueba y matriz de trazabilidad usando las plantillas.
- **Resultado recibido:** ejemplos aplicados en `verif/test-cases/` y `verif/verification-plan/`.
- **Revisión realizada:**
- **Cambios aplicados:**
- **Prueba agregada:**
- **Aprendizaje:**

## IA-006 — Captura separada de stdout y stderr (RF-11)

- **Integrante:** Oscar Aguilera
- **Objetivo:** que cada trabajo guarde su salida normal y sus errores por separado y que se puedan consultar (RF-11, TC-006).
- **Resultado recibido:** función `lanzar_trabajo()` que abre `data/salidas/<id>.out` y `data/salidas/<id>.err` y se los pasa a `Popen`; comandos `ejecutar <programa> &`, `salida <id>` y `errores <id>`.
- **Revisión realizada:** se probó con un programa que escribe en los dos flujos y termina con error (`sh -c "echo hola; echo fallo >&2; exit 3"`), con un programa que no existe, con cancelación y reiniciando Q-umplidor para revisar que la salida se pueda consultar después.
- **Cambios aplicados (deficiencia encontrada):** con un programa inexistente, `Popen` fallaba pero los archivos `.out` y `.err` ya se habían creado, y quedaban archivos de un trabajo que nunca se registró. Se agregó un `try/except OSError` que los borra antes de mostrar el error.
- **Prueba agregada:** caso TC-006 (ver evidencia en `verif/results/`).
- **Aprendizaje:** el hijo recibe su propia copia de los descriptores de archivo; el padre tiene que cerrar los suyos (por eso el `with`) o se quedan abiertos mientras corre Q-umplidor.

## IA-007 — Guías técnica y de usuario

- **Integrante:** Oscar Aguilera
- **Objetivo:** que las guías describan el código que realmente existe.
- **Resultado recibido:** borradores de `Arquitectura.md` y `guia-de-usuario.md`.
- **Revisión realizada:** se comparó cada componente, comando y archivo mencionado contra `src/main.py`, y se siguieron los pasos de instalación de la guía de usuario desde cero en WSL2.
- **Cambios aplicados:**
- **Prueba agregada:** Escenario A del plan de verificación (instalar e iniciar solo con la documentación).
- **Aprendizaje:** la versión anterior describía `cli.py` y `job_manager.py`, que nunca llegaron al repositorio; la documentación tiene que revisarse contra el código en cada avance.

## IA-008 — Comando para revisar el PR #129 (rechazado)

- **Integrante:** Oscar Aguilera
- **Objetivo:** ver desde la terminal el estado del PR #129, sus revisores y los issues que cierra (#127 y #128).
- **Resultado recibido:** un comando `gh pr view 129 --json state,title,reviewRequests,reviews,closingIssuesReferences ...`.
- **Revisión realizada:** se ejecutó en WSL2 con `gh` 2.46.0 antes de usarlo como referencia.
- **Motivo técnico del rechazo:** el comando falló con `Unknown JSON field: "closingIssuesReferences"`; ese campo no existe en la versión de `gh` instalada (la propia herramienta listó los campos válidos). La IA lo propuso sin considerar la versión del entorno.
- **Qué se hizo en su lugar:** se usó un comando solo con campos válidos (`state`, `title`, `reviewDecision`, `reviewRequests`, `reviews`), y los issues ligados se verificaron en la sección *Development* del PR en GitHub.
- **Prueba agregada:** no aplica (no se integró nada al repositorio).
- **Aprendizaje:** un resultado de la IA que depende de herramientas externas hay que probarlo en el entorno real; las opciones cambian entre versiones.

## IA-009 — Cancelación en cola y rechazo con cola llena

- **Integrante:** Oscar Aguilera
- **Objetivo:** implementar RF-10 (cancelar un trabajo que espera en la cola) y RF-25 / RNF-29 (rechazo explícito con la cola llena) sobre la cola de Diego (PR #130).
- **Resultado recibido:** cambios en `cancelar` y `registrar_en_cola()`, capacidad configurable con `Q_CAPACIDAD_COLA` y un script de prueba (`verif/scripts/prueba_cola.sh`) para TC-005 y TC-016.
- **Revisión realizada:** se corrió el script sobre cada commit: con el código original da FAIL y con los cambios da PASS en los dos casos. Se probó también un valor inválido de `Q_CAPACIDAD_COLA` y el reinicio.
- **Cambios aplicados (deficiencia encontrada):** la primera versión probada hacía tronar `estado` y `listar` con un trabajo cancelado en cola, porque `tiempo_trabajo()` restaba `None`. Se agregó la protección en un commit aparte (`bb8d932`) y se avisó en el PR #130, donde el error ya existía.
- **Prueba agregada:** TC-005 y TC-016 (`verif/results/TC-005-20261028/`, `verif/results/TC-016-20261028/`).
- **Aprendizaje:** la cancelación y el hilo de la cola deben decidir bajo el mismo candado; si no, un trabajo se puede cancelar y arrancar al mismo tiempo.

## IA-010 — Incidente INC-001 y guías con la cola

- **Integrante:** Oscar Aguilera
- **Objetivo:** documentar el incidente de la cancelación en cola y actualizar las guías.
- **Resultado recibido:** borrador de `INC-001.md` y secciones nuevas en las guías.
- **Revisión realizada:** se reprodujo el síntoma del incidente sobre el commit `9bc5c83` (el trabajo "cancelado" sí se ejecutaba) y se comprobaron los ejemplos de la guía contra el código.
- **Cambios aplicados:**
- **Prueba agregada:** TC-005 como prueba de regresión del incidente.
- **Aprendizaje:**

## IA-011 — Alias `queue cancelar <id>`

- **Integrante:** Oscar Aguilera
- **Objetivo:** que `queue cancelar <id>` cancele igual que `cancelar <id>`.
- **Resultado recibido:** al probarlo se encontró que `queue cancelar 2` formaba un trabajo nuevo con el texto "cancelar 2", bash respondía `command not found` (código 127) y el trabajo 2 no se cancelaba. Se propuso traducir `queue cancelar` a `cancelar` antes de interpretar el comando.
- **Revisión realizada:** se reprodujo el problema antes del cambio y se amplió TC-005 para cancelar un trabajo con el alias y comprobar que no se crea un trabajo nuevo.
- **Cambios aplicados:**
- **Prueba agregada:** TC-005 ampliado en `verif/scripts/prueba_cola.sh`.
- **Aprendizaje:**

## IA-012 — Límite de concurrencia, estados y tiempos, escalamiento

- **Integrante:** Ruy Valle
- **Objetivo:** implementar RF-05, RF-06 y RF-30 sobre el código de `main`, en módulos separados para no tocar el código de los demás.
- **Resultado recibido:** `concurrencia.py`, `estados.py`, `escalamiento.py` y la integración en `main.py`. La cola pasó de un hilo a un despachador con límite.
- **Revisión realizada:** pruebas reales con `ps`, en lugar de solo leer el código:
  - el límite nunca se supera;
  - un programa que ignora SIGTERM se fuerza con SIGKILL;
  - con un trabajo de shell, el código original dejaba `sleep 99` huérfano con padre 1.
- **Cambios aplicados:** la revisión encontró dos fallas en el primer resultado, y se corrigieron antes de integrar:
  - La hora de fin de los trabajos con `&` se anotaba hasta que alguien consultaba, así que un `sleep 3` salía con 4 s. Se agregó `registrar_terminados()`.
  - Al cerrar Q-umplidor, el motivo decía "cancelado por el usuario".
  - Además se quitaron cuatro funciones duplicadas por un merge anterior.
- **Prueba agregada:** TC-020, TC-021, TC-022, TC-023 y TC-027 en `verif/scripts/prueba_avance02_ruy.py`.
- **Aprendizaje:** contar los procesos vivos en vez de llevar un contador evita que el límite se desincronice; para defenderlo, hay que demostrarlo con `ps`, no con lo que imprime el programa.

## IA-013 — ADR-0004..0007 y documento de arquitectura

- **Integrante:** Ruy Valle
- **Objetivo:** documentar las decisiones de concurrencia, persistencia, recuperación y cancelación tal como quedaron en el código.
- **Resultado recibido:** cuatro ADR con el formato de los existentes y `ArquitecturaSistema.md` (arquitectura actual y objetivo).
- **Revisión realizada:**
  - Se comparó cada afirmación contra el código.
  - Se validaron los diagramas Mermaid generándolos con `mmdc`.
  - Al redactar ADR-0006 se probó el cierre por SIGHUP y apareció el problema de INC-002.
- **Cambios aplicados:**
  - ADR-0002 y ADR-0003 se marcaron como reemplazados en lugar de borrarlos.
  - Se corrigió el código para el cierre por señal antes de documentarlo.
- **Prueba agregada:** TC-026.
- **Aprendizaje:** escribir el ADR obliga a probar los caminos de salida que nadie había probado.

## IA-014 — Recuperación de huérfanos, script de verificación e INC-002

- **Integrante:** Ruy Valle
- **Objetivo:**
  - Corregir el estado imposible tras `kill -9`: el trabajo aparecía `INTERRUPTED` mientras seguía corriendo.
  - Corregir el mensaje contradictorio con la cola llena.
  - Generar evidencia reproducible.
- **Resultado recibido:** `recuperacion.py` (huella pid + inicio del proceso + `boot_id`), la corrección en `lanzar_o_encolar` y un script con 8 casos que verifica PASS/FAIL automáticamente.
- **Revisión realizada:**
  - Se ejecutó el script contra el código anterior y contra el corregido.
  - **Se rechazó la primera versión del script por dos defectos:**
    - TC-022 medía el tiempo sin esperar la respuesta de Q-umplidor, así que daba un FAIL falso.
    - Dependía de un campo nuevo de `trabajos.json`, así que no servía para probar el código viejo.
- **Cambios aplicados:**
  - El script espera el mensaje de Q-umplidor.
  - Ubica los procesos con `ps` en vez de con `trabajos.json`, para funcionar con cualquier versión.
  - Con eso, el código anterior da FAIL en TC-025 y TC-027, y el corregido da PASS en los 8.
  - Al correr **todos** los scripts del repo con el código integrado, TC-005 y TC-016 de Oscar (`prueba_cola.sh`) fallaban: suponían una cola de un trabajo a la vez y el formato anterior de `estado`/`listar`. Se fijó `Q_LIMITE_CONCURRENCIA=1` en su escenario y sus `grep` aceptan los nombres del cliente. Volvieron a PASS.
  - El caso 7 de `test_avance1_completo.py` (IA-003) ya fallaba en `main`: cancelaba el trabajo 1 y luego esperaba que `codigo 1` diera 0. Ahora consulta el trabajo 2, que termina normal. Queda 8/8.
- **Prueba agregada:** TC-024, TC-025 y TC-026; regresión de INC-002.
- **Aprendizaje:** un script de verificación también hay que verificarlo: debe fallar con el código que tiene el error.
