# Guía de usuario de Q-umplidor

Responsable: Oscar Aguilera

Esta guía explica cómo arrancar Q-umplidor y cómo usar los comandos que ya funcionan. Lo que se está haciendo para el Avance 02 lo dejamos al final como pendiente; lo vamos a ir pasando arriba conforme se integre y se pruebe.

## ¿Qué necesito?

- Linux. Nosotros lo probamos en WSL2 con Ubuntu, pero una VM o Linux nativo también sirven. En macOS no lo recomendamos porque no tiene `/proc`.
- Python 3.10 o más nuevo. Para revisarlo: `python3 --version`
- No hay que instalar librerías, todo es biblioteca estándar.

## Cómo arrancarlo

```bash
git clone https://github.com/Qiskit421/Q-umplidor.git
cd Q-umplidor
python3 src/main.py
```

Si todo salió bien aparece esto y ya puedes escribir comandos:

```text
Q-umplidor>
```

Para salir se usa `Ctrl + D` (o `Ctrl + C`).

## Comandos que ya funcionan

- `help` — enseña la lista de comandos.
- `sleep N` — hace una espera de N segundos en primer plano. Mientras dura no puedes escribir otra cosa.
- `sleep N &` — manda el trabajo a segundo plano y te da su ID para seguirlo. La consola queda libre.
- `estado ID` — dice qué comando es, en qué estado va y cuántos segundos lleva.
- `listar` — enseña todos los trabajos de la sesión.
- `codigo ID` — dice con qué código de salida terminó un trabajo. Si sigue corriendo, te avisa que todavía no tiene.
- `cancelar ID` — detiene un trabajo. Primero le manda SIGTERM y si en 2 segundos no se muere, le manda SIGKILL.
- `ejecutar PROGRAMA [argumentos] &` — corre cualquier programa en segundo plano y te da su ID. Por ejemplo `ejecutar ls -l /tmp &`.
- `salida ID` — enseña lo que el trabajo imprimió normalmente (stdout).
- `errores ID` — enseña los mensajes de error del trabajo (stderr), por separado de la salida normal.

### Ejemplo

Esto es una sesión normal:

```text
Q-umplidor> sleep 30 &
ID: [1]
Q-umplidor> estado 1
[1] sleep 30 & -> En ejecución (3s)
Q-umplidor> cancelar 1
Trabajo [1] cancelado
Q-umplidor> codigo 1
codigo: el trabajo [1] terminó con código de salida 143
```

Ese `143` quiere decir que el proceso no terminó por sí solo, lo terminó una señal: se calcula como 128 + 15, y la 15 es SIGTERM. Es el mismo número que daría Bash. Si saliera `137` (128 + 9) sería porque hubo que usar SIGKILL.

### Ver la salida y los errores de un trabajo

```text
Q-umplidor> ejecutar sh -c "echo hola; echo fallo >&2; exit 3" &
ID: [2]
Q-umplidor> salida 2
hola
Q-umplidor> errores 2
fallo
Q-umplidor> codigo 2
codigo: el trabajo [2] terminó con código de salida 3
```

Cada trabajo guarda su salida en `data/salidas/ID.out` y sus errores en `data/salidas/ID.err`, así que también los puedes abrir directamente desde la terminal.

### Estados que vas a ver

- **En ejecución:** el proceso sigue vivo.
- **Terminado:** acabó bien, con código 0.
- **Falló (código N):** acabó con algún error.
- **En cola:** está esperando su turno en la cola.
- **Cancelado:** lo detuviste con `cancelar`, ya sea mientras corría o mientras esperaba en la cola.
- **Interrumpido:** estaba corriendo cuando se cerró o se reinició Q-umplidor.

### Si algo sale mal

Q-umplidor no se cierra cuando escribes algo mal, solo te avisa:

- `comando no reconocido` → ese comando no existe, revisa `help`.
- `falta el ID del trabajo` → te faltó poner el número, por ejemplo `estado 1`.
- `el ID debe ser un número` → pusiste letras en lugar del ID.
- `no existe el trabajo [N]` → ese ID no está registrado; usa `listar` para ver cuáles hay.
- `los segundos deben ser un entero no negativo` → en `sleep` solo van números enteros de 0 para arriba.
- `ejecutar: no se pudo iniciar 'X'` → ese programa no existe o no está en el PATH. El trabajo no se registra.
- `ejecutar: uso: ejecutar <programa> [argumentos] &` → te faltó el programa o el `&` al final.
- `no ha escrito nada en la salida estándar` → el trabajo existe pero no imprimió nada (todavía).

### La cola de trabajos

Con `queue` mandas trabajos a una fila: se ejecutan **de uno en uno, en el orden en que llegaron**, y cada uno empieza cuando termina el anterior.

- `queue COMANDO` — agrega el comando al final de la cola y te da su ID. Por ejemplo `queue sleep 5` o `queue echo hola`.
- `queue` (solo) — enseña los trabajos de la cola con su archivo de salida y el tiempo que les queda.
- `cancelar ID` — también sirve para un trabajo que **sigue esperando**: se quita de la fila y nunca llega a ejecutarse.

```text
Q-umplidor> queue sleep 5
ID: [1] agregado a la cola
Q-umplidor> queue sleep 5
ID: [2] agregado a la cola
Q-umplidor> cancelar 2
Trabajo [2] cancelado (estaba en cola, no llegó a ejecutarse)
Q-umplidor> estado 2
[2] sleep 5 -> Cancelado (0s)
```

#### Cola llena

La cola acepta como máximo **5 trabajos esperando** (el que se está ejecutando no cuenta). Si ya está llena, el trabajo nuevo se rechaza en ese momento, no se registra y no gasta un ID:

```text
queue: cola llena (5/5 en espera), trabajo rechazado. Intenta de nuevo cuando avance la cola.
```

Para cambiar la capacidad, arranca Q-umplidor con la variable `Q_CAPACIDAD_COLA`:

```bash
Q_CAPACIDAD_COLA=2 python3 src/main.py
```

Tiene que ser un número entero de 1 para arriba; si no, Q-umplidor no arranca y te dice por qué.

### Qué pasa si cierro Q-umplidor

El historial se guarda en `data/trabajos.json`. Al volver a abrir, `listar` sigue mostrando tus trabajos y los IDs continúan donde se quedaron. Los trabajos que seguían corriendo se detienen al salir y aparecen como **Interrumpido**. Los que seguían esperando en la cola se vuelven a formar y se ejecutan al arrancar otra vez. Su salida y sus errores se pueden seguir consultando.

### Lo que todavía no hace

- La cola ejecuta un trabajo a la vez; todavía no hay un límite de concurrencia configurable.

## Pendiente para el Avance 02

Esto todavía no está integrado en `main`. Cuando Ingeniería lo termine, lo probamos y lo movemos a la sección de arriba con su comando real:

- [ ] Límite de concurrencia que se pueda configurar.
- [ ] Horas de envío, inicio y fin en `estado` y `listar`.
- [ ] Escalamiento: si un trabajo no hace caso a SIGTERM, mandarle SIGKILL después de un tiempo.
- [ ] Bitácora con fecha y hora de cada cosa que pasa.
