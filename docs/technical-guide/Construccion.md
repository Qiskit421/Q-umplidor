# Código y mecanismo de construcción

> **Responsable:** Oscar Aguilera. Cumple el punto "Construcción y dependencias" del estándar del cliente (doc. 04): *"El repositorio deberá incluir un mecanismo de construcción reproducible. Toda dependencia deberá declararse, justificar su propósito y fijar una versión o requisito compatible cuando sea necesario."*

## 1. Resumen

| Pregunta | Respuesta |
|---|---|
| Lenguaje | Python 3, **3.10 o más nuevo** (ADR-0001) |
| Sistema operativo | Linux o WSL 2 (Ubuntu). El código también arranca en Windows, pero las señales, `/proc` y los grupos de procesos (`killpg`) solo están completos en Linux. |
| Dependencias externas | **Ninguna.** Solo biblioteca estándar. No hay `requirements.txt` porque no hay nada que instalar con `pip`. |
| ¿Se compila? | Python no genera un ejecutable. "Construir" es comprobar, siempre de la misma forma, que el código está listo: versión de Python, dependencias, compilación sin advertencias, análisis estático y pruebas. |
| Comando | `./construir.sh` (rápido) o `./construir.sh --completo` (también las pruebas del Avance 01 y de red; con Q-umplidor cerrado) |
| Binarios en el repo | Ninguno. `__pycache__/` y `data/` están en `.gitignore`. |

## 2. Requisitos y por qué

| Requisito | Versión | Para qué | Cómo revisarlo |
|---|---|---|---|
| Python 3 | ≥ 3.10 | Todo el sistema. Se pide 3.10 porque `construir.sh` usa `sys.stdlib_module_names` y es la versión mínima con la que se probó; Ubuntu 22.04 trae 3.10 y Ubuntu 24.04 trae 3.12. | `python3 --version` |
| Bash | cualquiera | Correr `construir.sh` y los comandos de la cola (`queue ...` usa `/bin/bash`) | `bash --version` |
| Git | cualquiera | Clonar el repositorio | `git --version` |
| pyflakes | opcional | Análisis estático en `construir.sh`. Si no está, ese paso dice `OMITIDO` y no cuenta como falla. | `python3 -m pyflakes --version` |

Instalación en Ubuntu / WSL:
```bash
sudo apt update
sudo apt install -y python3 git
sudo apt install -y pyflakes3      # opcional
```

**Módulos de la biblioteca estándar que se usan** (ninguno se instala aparte): `subprocess`, `signal`, `os`, `threading`, `socket`, `json`, `shlex`, `pathlib`, `collections`, `atexit`, `secrets`, `io`, `datetime`, `fcntl` (Linux), `ctypes` y `msvcrt` (solo Windows). El paso 2 de `construir.sh` comprueba que no aparezca ningún otro.

## 3. Desde un clon limpio

```bash
git clone https://github.com/Qiskit421/Q-umplidor.git
cd Q-umplidor
./construir.sh
```

Si dice `Permission denied`, usa `bash construir.sh` o dale permiso una vez con `chmod +x construir.sh`.

Salida esperada (resumida):
```
== 1. Python
   OK  Python 3.12 (se necesita 3.10 o más nuevo)
== 2. Dependencias
   OK  solo biblioteca estándar de Python (ADR-0001); no hay nada que instalar
== 3. Compilación con advertencias como errores
   OK  src/, verif/scripts/ y verif/test-cases/ compilan sin advertencias
== 4. Análisis estático (pyflakes)
   OK  sin avisos
== 5. Pruebas unitarias
   OK  bitácora y protocolo
CONSTRUCCIÓN: OK
```

`./construir.sh --completo` es el **único comando documentado** que corre todas las pruebas automatizadas que funcionan hoy (RNF-20).

Termina con código de salida `0` si todo pasó y `1` si algo falló, así que se puede usar en otros scripts: `./construir.sh && python3 src/servidor.py`.

## 4. Qué hace cada paso

| Paso | Comando que corre | Qué detiene |
|---|---|---|
| 1. Python | `python3 -c 'import sys; ...'` | Python ausente o anterior a 3.10 |
| 2. Dependencias | Recorre con `ast` todos los `import` de `src/` | Cualquier import que no sea de la biblioteca estándar ni de `src/`: una dependencia sin declarar |
| 3. Compilación | `python3 -W error -m compileall -q src verif/scripts verif/test-cases` | Errores de sintaxis y advertencias del compilador (`-W error` las vuelve errores). Compila a una carpeta temporal (`PYTHONPYCACHEPREFIX`) para no dejar `__pycache__` en el repo. |
| 4. Análisis estático | `python3 -m pyflakes src verif/scripts verif/test-cases` | Imports y variables sin usar, nombres no definidos, f-strings sin valores |
| 5. Pruebas unitarias | `python3 -m unittest discover -s verif/test-cases -q` | `test_event_log.py` (bitácora) y `test_protocolo.py` (mensajes fragmentados, RF-21) |
| 6. Avance 01 (`--completo`) | `python3 verif/scripts/test_avance1_completo.py` | CP-001 a CP-008 (enviar, ID, estado, listar, cancelar, código, comando inválido). Abre `src/main.py` de verdad, así que Q-umplidor debe estar cerrado. Unos 6 s. |
| 7. Red (`--completo`) | `python3 verif/scripts/prueba_red.py` | TC-028 a TC-037. Necesita el puerto 5000 libre; guarda evidencia en `verif/results/TC-028-037-<fecha>/` (la reemplaza si ya existe una del mismo día). Unos 5 s. |

## 5. Ejecutar

| Para | Comando |
|---|---|
| Consola local | `python3 src/main.py` |
| Servidor de red (consola local + clientes remotos) | `python3 src/servidor.py` — muestra IP, puerto 5000 y la clave de 6 dígitos |
| Cliente remoto | `python3 src/cliente.py` (busca el servidor en la red local) o `python3 src/cliente.py <ip>` |
| Ayuda de comandos | `help`, dentro de la consola o del cliente |

Configuración con variables de entorno, puestas antes del comando (por ejemplo `Q_LIMITE_CONCURRENCIA=3 python3 src/servidor.py`):

| Variable | Por defecto | Qué controla |
|---|---|---|
| `Q_LIMITE_CONCURRENCIA` | 2 | Trabajos de la cola corriendo al mismo tiempo (también `limite N`) |
| `Q_CAPACIDAD_COLA` | 5 | Trabajos esperando en la cola antes de rechazar |
| `Q_GRACIA_SIGTERM` | 2 s | Espera entre SIGTERM y SIGKILL al cancelar |
| `Q_TIEMPO_MAXIMO` | 0 (sin límite) | Tiempo máximo de un trabajo de la cola |
| `Q_INACTIVIDAD` | 300 s | Segundos sin mensajes antes de desconectar a un cliente de red |

Un valor inválido detiene el arranque con un mensaje que dice qué variable está mal.

Los datos se guardan en `data/` dentro del repositorio (`trabajos.json`, `events.jsonl`, `salidas/`). Para empezar de cero: cierra Q-umplidor y borra esa carpeta.

## 6. Pruebas

| Qué | Comando | Estado |
|---|---|---|
| Construcción completa | `./construir.sh --completo` | Funciona |
| Unitarias | `python3 -m unittest discover -s verif/test-cases -v` | Funciona (17 pruebas) |
| Red, TC-028 a TC-037 | `python3 verif/scripts/prueba_red.py [TC-0XX]` | Funciona |
| Avance 01, CP-001 a CP-008 | `python3 verif/scripts/test_avance1_completo.py` | Funciona (8/8) |
| Cola, TC-005 y TC-016 | `bash verif/scripts/prueba_cola.sh` | **Desactualizado:** desde el PR #155, `cancelar <id>` ya no ve los trabajos de la cola (ahora es `queue cancelar <id>`) y TC-005 da FAIL. Está fuera de `construir.sh` hasta que se actualice. |
| Avance 02, TC-020 a TC-027 | `python3 verif/scripts/prueba_avance02_ruy.py` | **Desactualizado:** TC-020 se detiene con `KeyError`. Fuera de `construir.sh` hasta que se actualice. |

## 7. Problemas comunes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| `Q-umplidor ya está abierto en otra terminal` | Otro `main.py` o `servidor.py` usa la misma carpeta `data/` (candado `data/q-umplidor.lock`) | Cierra el otro. Si no hay otro, el candado se libera solo al cerrarse el proceso. |
| `No se pudo abrir el puerto 5000 para la red` | Otro servidor de Q-umplidor (u otro programa) ya usa el puerto | Ciérralo. Para ver quién lo usa: `ss -ltnp \| grep 5000` |
| `El puerto 5000 está ocupado` al correr `prueba_red.py` | Lo mismo | Cierra el servidor y vuelve a correr la prueba |
| `No se pudo cargar data/trabajos.json` | El archivo se editó a mano o está dañado | Revísalo o bórralo (pierdes el historial de la cola) |
| `cd ~/Q-umplidor: El sistema no puede encontrar la ruta` | Estás en `cmd` de Windows, no en Ubuntu | Escribe `wsl` primero |
