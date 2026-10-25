# Guía técnica — Arquitectura de Q-umplidor

> **Estado:** Avance 02. Describe lo que hay en `src/main.py` en la rama `main`. Lo que todavía no está integrado aparece en la sección 8 como pendiente. Si algo de aquí no coincide con el código, manda el código y hay que corregir este documento.

Responsable: Oscar Aguilera

## 1. Propósito

Q-umplidor es un gestor de trabajos para Linux. Recibe comandos en una consola interactiva, ejecuta cada trabajo como un proceso hijo del sistema operativo y permite consultar su estado, su salida y su código de salida, cancelarlo y conservar el historial entre reinicios.

## 2. Vista general

Todo el sistema vive hoy en un solo archivo, `src/main.py`, con biblioteca estándar de Python 3 (ADR-0001). Internamente se separa en cuatro partes:

```mermaid
flowchart TD
    U["Usuario (terminal)"] -->|escribe comandos| C["Consola<br/>ciclo while True + input()"]
    C -->|crea / consulta / cancela| T["Tabla de trabajos<br/>diccionario trabajos"]
    C -->|lanza| L["lanzar_trabajo()<br/>subprocess.Popen"]
    L -->|un proceso por trabajo| P["Procesos hijos"]
    P -->|stdout| O["data/salidas/&lt;id&gt;.out"]
    P -->|stderr| E["data/salidas/&lt;id&gt;.err"]
    T -->|guardar_trabajos()| J["data/trabajos.json"]
    J -->|cargar_trabajos() al iniciar| T
```

## 3. Componentes

| Componente | Dónde está | Qué hace |
|---|---|---|
| Consola | Ciclo `while True` al final de `main.py` | Muestra el prompt `Q-umplidor>`, separa el comando en palabras y llama a la parte que corresponde. Un comando inválido solo imprime un aviso. |
| Tabla de trabajos | Diccionario global `trabajos` y contador `siguiente_id` | Guarda por ID: proceso, comando, inicio, fin, estado, código y si se canceló. |
| Lanzamiento | `lanzar_trabajo()` y `registrar_trabajo()` | Crea el proceso hijo con su stdout y stderr redirigidos a archivos, y lo agrega a la tabla. |
| Supervisión | `actualizar_trabajo()` / `estado_trabajo()` | Llama `poll()` al proceso. Si ya terminó, guarda código y hora de fin, decide el estado final y lo persiste. |
| Persistencia | `guardar_trabajos()` / `cargar_trabajos()` | Escribe y lee `data/trabajos.json`. |
| Consulta de salidas | `mostrar_archivo()` | Lee el archivo `.out` o `.err` de un trabajo. |

## 4. Comandos

| Comando | Qué hace internamente |
|---|---|
| `sleep N` | `time.sleep(N)` en el mismo proceso (primer plano). |
| `sleep N &` | Lanza `python3 -c "import time; time.sleep(N)"` como hijo. |
| `ejecutar <programa> [args] &` | Separa los argumentos con `shlex.split` y lanza el programa sin shell. |
| `estado <id>` / `listar` | Actualizan cada trabajo con `poll()` y muestran estado y tiempo. |
| `codigo <id>` | Muestra el código guardado. Si murió por señal, lo muestra como Bash (`128 + señal`, por ejemplo 143 para SIGTERM). |
| `salida <id>` / `errores <id>` | Muestran `data/salidas/<id>.out` o `.err`. |
| `cancelar <id>` | SIGTERM, espera hasta 2 s, SIGKILL si no terminó, y `wait()`. |

## 5. Procesos, salidas y recursos

**Un proceso por trabajo.** Cada trabajo corre en su propio proceso (`subprocess.Popen`), no en un hilo. Así corren en paralelo de verdad, se pueden detener con señales y si uno falla no tumba la consola.

**stdout y stderr separados (RF-11).** `lanzar_trabajo()` abre dos archivos por trabajo y se los da a `Popen` como `stdout` y `stderr`. El hijo escribe directo en ellos, aunque la consola esté esperando otro comando, y la salida se puede consultar aunque Q-umplidor se reinicie.

**Descriptores de archivo.** El hijo recibe su propia copia de los descriptores. El padre abre los archivos dentro de un `with`, así que los cierra en cuanto el hijo arrancó y no se acumulan archivos abiertos.

**Entrada estándar.** Los trabajos reciben `stdin=DEVNULL`, para que no puedan leer lo que el usuario escribe en la consola.

**Programa inexistente.** Si `Popen` lanza `OSError`, se borran los dos archivos recién creados, se muestra el error y no se registra el trabajo ni se consume un ID.

**Recolección de hijos (zombis).** El código de salida de un hijo se lee con `poll()` cuando alguien consulta (`estado`, `listar`, `codigo`, `cancelar`) y con `wait()` al cancelar. Hasta esa consulta, un hijo que terminó solo queda como zombi (`Z` en `ps`). Ver pendientes.

## 6. Estados

| Estado en el código | Cuándo |
|---|---|
| En ejecución | El proceso sigue vivo (`poll()` devuelve `None`). |
| Terminado | Terminó con código 0. |
| Falló (código N) | Terminó con código distinto de 0 y no fue cancelado. |
| Cancelado | Se pidió `cancelar`. |
| Interrumpido | Estaba en ejecución cuando Q-umplidor se cerró o se reinició. |

El modelo completo (con `QUEUED`) está en [ModeloDeEstados.md](ModeloDeEstados.md). El cliente pide como mínimo `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED` y `CANCELED` (RF-06); los nombres en español del código deben quedar mapeados a esos.

## 7. Persistencia y recuperación

- **Formato:** `data/trabajos.json` con `siguiente_id` y la lista de trabajos (sin el objeto `Popen`, que no se puede guardar).
- **Escritura atómica:** se escribe en `trabajos.tmp` y luego `os.replace()` lo cambia por el archivo real. Si el programa muere a mitad, queda el archivo anterior completo, nunca uno a medias.
- **Al arrancar:** `cargar_trabajos()` valida IDs (enteros, positivos, sin repetir) y el contador. Si el archivo está dañado, el programa se detiene con un mensaje en vez de arrancar con datos inválidos.
- **Recuperación:** los trabajos que estaban "En ejecución" pasan a "Interrumpido", porque sus procesos ya no pertenecen a esta sesión.
- **Al salir normalmente:** los trabajos activos se terminan (SIGTERM → SIGKILL), se marcan como "Interrumpido" y se guarda el archivo.
- **Salidas:** los archivos de `data/salidas/` no se borran al reiniciar, por eso `salida` y `errores` siguen funcionando con trabajos anteriores.

La decisión real es JSON con escritura atómica, no SQLite: el ADR-0003 debe actualizarse para reflejarlo.

## 8. Pendientes del Avance 02

| Tema | Requisito | Responsable |
|---|---|---|
| Cola de trabajos | RF-03 | Diego |
| Límite configurable de concurrencia | RF-05 | Ruy |
| Estados y tiempos (nombres del cliente) | RF-06 | Ruy |
| Escalamiento documentado de la cancelación | RF-30 | Ruy |
| Cancelación de trabajos en cola | RF-10 | Oscar |
| Rechazo explícito con cola llena | RF-25, RNF-29 | Oscar |
| Bitácora de eventos | — | Marlene |
| Solicitudes concurrentes o duplicadas | RF-26 | Marlene |
| Liberación de recursos (recolectar hijos sin esperar una consulta) | — | Marlene |

Cuando la cola exista, `lanzar_trabajo()` es el punto donde la cola debe arrancar cada trabajo, para que todos conserven la captura de stdout y stderr.

## 9. Decisiones relacionadas

| ADR | Tema |
|---|---|
| [ADR-0001](../decisions/ADR-0001.md) | Python 3 con biblioteca estándar |
| [ADR-0002](../decisions/ADR-0002.md) | Concurrencia: un proceso por trabajo, cola con pool de hilos |
| [ADR-0003](../decisions/ADR-0003.md) | Persistencia |
