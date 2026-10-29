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

## IA-008 — (resultado rechazado)

- **Integrante:**
- **Objetivo:**
- **Resultado recibido:**
- **Revisión realizada:**
- **Motivo técnico del rechazo:**
- **Prueba agregada:**
- **Aprendizaje:**
