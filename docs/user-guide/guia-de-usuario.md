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
- **Cancelado:** lo detuviste con `cancelar`.
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

### Qué pasa si cierro Q-umplidor

El historial se guarda en `data/trabajos.json`. Al volver a abrir, `listar` sigue mostrando tus trabajos y los IDs continúan donde se quedaron. Los trabajos que seguían corriendo se detienen al salir y aparecen como **Interrumpido**. Su salida y sus errores se pueden seguir consultando.

### Lo que todavía no hace

- No hay límite de trabajos a la vez ni cola.

## Pendiente para el Avance 02

Esto todavía no está integrado en `main`. Cuando Ingeniería lo termine, lo probamos y lo movemos a la sección de arriba con su comando real:

- [ ] Cola de trabajos: si ya se llegó al límite, el trabajo espera en `QUEUED`.
- [ ] Límite de concurrencia que se pueda configurar.
- [ ] Horas de envío, inicio y fin en `estado` y `listar`.
- [ ] Poder cancelar un trabajo que todavía está en la cola.
- [ ] Escalamiento: si un trabajo no hace caso a SIGTERM, mandarle SIGKILL después de un tiempo.
- [ ] Bitácora con fecha y hora de cada cosa que pasa.
- [ ] Mensaje claro cuando la cola esté llena, sin registrar el trabajo.
