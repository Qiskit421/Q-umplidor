import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import threading
from collections import deque

ARCHIVO_TRABAJOS = Path(__file__).resolve().parent.parent / "data" / "trabajos.json"
CARPETA_SALIDAS = ARCHIVO_TRABAJOS.parent / "salidas"


def rutas_salida(id_trabajo):
    """Cada trabajo tiene dos archivos: uno para stdout y otro para stderr."""
    return (
        CARPETA_SALIDAS / f"{id_trabajo}.out",
        CARPETA_SALIDAS / f"{id_trabajo}.err",
    )


def lanzar_trabajo(id_trabajo, argumentos):
    """Lanza el proceso hijo con stdout y stderr redirigidos a archivos separados."""
    CARPETA_SALIDAS.mkdir(parents=True, exist_ok=True)
    ruta_out, ruta_err = rutas_salida(id_trabajo)
    # El hijo recibe su propia copia de los descriptores. El padre cierra los
    # suyos al salir del "with" para no dejar archivos abiertos.
    try:
        with ruta_out.open("wb") as salida, ruta_err.open("wb") as errores:
            return subprocess.Popen(
                argumentos,
                stdin=subprocess.DEVNULL,
                stdout=salida,
                stderr=errores,
            )
    except OSError:
        # Si el programa no existe, no dejamos archivos de un trabajo que nunca se registró.
        ruta_out.unlink(missing_ok=True)
        ruta_err.unlink(missing_ok=True)
        raise


def registrar_trabajo(proceso, entrada):
    """Guarda el trabajo recién lanzado y muestra su ID."""
    global siguiente_id
    trabajos[siguiente_id] = {
        "proceso": proceso,
        "comando": entrada,
        "inicio": time.time(),
        "fin": None,
        "estado": "En ejecución",
        "codigo": None,
        "cancelado": False,
    }
    print(f"ID: [{siguiente_id}]")
    siguiente_id += 1
    guardar_trabajos()


def mostrar_archivo(id_trabajo, indice, comando, descripcion):
    """Muestra el contenido de stdout (indice 0) o stderr (indice 1) de un trabajo."""
    ruta = rutas_salida(id_trabajo)[indice]
    if not ruta.exists():
        print(f"{comando}: el trabajo [{id_trabajo}] no tiene {descripcion} registrada")
        return
    contenido = ruta.read_text(encoding="utf-8", errors="replace")
    if contenido:
        print(contenido, end="" if contenido.endswith("\n") else "\n")
    else:
        print(f"{comando}: el trabajo [{id_trabajo}] no ha escrito nada en {descripcion}")


def rutas_salida(id_trabajo):
    """Cada trabajo tiene dos archivos: uno para stdout y otro para stderr."""
    return (
        CARPETA_SALIDAS / f"{id_trabajo}.out",
        CARPETA_SALIDAS / f"{id_trabajo}.err",
    )


def lanzar_trabajo(id_trabajo, argumentos):
    """Lanza el proceso hijo con stdout y stderr redirigidos a archivos separados."""
    CARPETA_SALIDAS.mkdir(parents=True, exist_ok=True)
    ruta_out, ruta_err = rutas_salida(id_trabajo)
    # El hijo recibe su propia copia de los descriptores. El padre cierra los
    # suyos al salir del "with" para no dejar archivos abiertos.
    try:
        with ruta_out.open("wb") as salida, ruta_err.open("wb") as errores:
            return subprocess.Popen(
                argumentos,
                stdin=subprocess.DEVNULL,
                stdout=salida,
                stderr=errores,
            )
    except OSError:
        # Si el programa no existe, no dejamos archivos de un trabajo que nunca se registró.
        ruta_out.unlink(missing_ok=True)
        ruta_err.unlink(missing_ok=True)
        raise


def registrar_trabajo(proceso, entrada):
    """Guarda el trabajo recién lanzado y muestra su ID."""
    global siguiente_id
    trabajos[siguiente_id] = {
        "proceso": proceso,
        "comando": entrada,
        "inicio": time.time(),
        "fin": None,
        "estado": "En ejecución",
        "codigo": None,
        "cancelado": False,
    }
    print(f"ID: [{siguiente_id}]")
    siguiente_id += 1
    guardar_trabajos()


# Capacidad máxima de trabajos esperando en la cola (RF-25). Se configura con la
# variable de entorno Q_CAPACIDAD_COLA, por ejemplo: Q_CAPACIDAD_COLA=3 python3 src/main.py
def leer_capacidad_cola():
    valor = os.environ.get("Q_CAPACIDAD_COLA", "5")
    try:
        capacidad = int(valor)
        if capacidad < 1:
            raise ValueError
    except ValueError:
        raise SystemExit(f"Q_CAPACIDAD_COLA debe ser un entero mayor o igual a 1 (se recibió '{valor}')")
    return capacidad


CAPACIDAD_COLA = leer_capacidad_cola()

# Cola exclusiva para comandos "queue sleep N".
# Se reutilizan lanzar_trabajo() y rutas_salida() para capturar stdout/stderr.
cola_ids = deque()
condicion_cola = threading.Condition()
cola_cerrandose = False
id_cola_activo = None


def registrar_en_cola(comando, entrada):
    """Registra cualquier comando pendiente y lo agrega al final de la cola."""
    global siguiente_id
    with condicion_cola:
        en_espera = len(cola_ids)
    if en_espera >= CAPACIDAD_COLA:
        # Rechazo explícito (RF-25, RNF-29): no se registra, no consume ID y no bloquea.
        print(f"queue: cola llena ({en_espera}/{CAPACIDAD_COLA} en espera), trabajo rechazado. "
              "Intenta de nuevo cuando avance la cola.")
        return
    id_trabajo = siguiente_id
    ruta_out, ruta_err = rutas_salida(id_trabajo)
    CARPETA_SALIDAS.mkdir(parents=True, exist_ok=True)
    ruta_out.touch(exist_ok=True)
    ruta_err.touch(exist_ok=True)
    try:
        palabras = shlex.split(comando) if comando else []
    except ValueError:
        # La cola acepta el texto tal cual; el shell registrará el error al ejecutarlo.
        palabras = []
    segundos = 0
    if len(palabras) == 2 and palabras[0] == "sleep":
        try:
            segundos = max(0, int(palabras[1]))
        except ValueError:
            pass
    trabajos[id_trabajo] = {
        "proceso": None, "comando": entrada, "argumentos_cola": comando,
        "inicio": None, "fin": None, "estado": "En cola", "codigo": None,
        "cancelado": False, "es_cola": True,
        "segundos_solicitados": segundos,
        "momento_encolado": time.time(),
    }
    siguiente_id += 1
    guardar_trabajos()
    with condicion_cola:
        cola_ids.append(id_trabajo)
        condicion_cola.notify()
    print(f"ID: [{id_trabajo}] agregado a la cola")


def procesar_cola():
    """Ejecuta los comandos de queue de uno en uno, respetando el orden."""
    global id_cola_activo
    while True:
        with condicion_cola:
            while not cola_ids and not cola_cerrandose:
                condicion_cola.wait()
            if cola_cerrandose:
                return
            id_trabajo = cola_ids.popleft()
            trabajo = trabajos.get(id_trabajo)
            if trabajo is None or trabajo.get("cancelado"):
                continue
            id_cola_activo = id_trabajo

        try:
            trabajo["inicio"] = time.time()
            trabajo["estado"] = "En ejecución"
            guardar_trabajos()
            # Los sleep de la cola se ejecutan con Python para que funcionen
            # tanto en Windows como en Linux/WSL. Los demás comandos usan el shell.
            CARPETA_SALIDAS.mkdir(parents=True, exist_ok=True)
            ruta_out, ruta_err = rutas_salida(id_trabajo)
            comando = trabajo["argumentos_cola"]
            try:
                palabras = shlex.split(comando)
            except ValueError:
                palabras = []

            argumentos_sleep = None
            if len(palabras) == 2 and palabras[0] == "sleep":
                try:
                    segundos_sleep = int(palabras[1])
                    if segundos_sleep >= 0:
                        argumentos_sleep = [
                            sys.executable,
                            "-c",
                            f"import time; time.sleep({segundos_sleep})",
                        ]
                except ValueError:
                    pass

            with ruta_out.open("wb") as salida, ruta_err.open("wb") as errores:
                if argumentos_sleep is not None:
                    proceso = subprocess.Popen(
                        argumentos_sleep,
                        stdin=subprocess.DEVNULL,
                        stdout=salida,
                        stderr=errores,
                    )
                else:
                    proceso = subprocess.Popen(
                        comando,
                        shell=True,
                        executable="/bin/bash" if os.name == "posix" else None,
                        stdin=subprocess.DEVNULL,
                        stdout=salida,
                        stderr=errores,
                    )

            trabajo["proceso"] = proceso
            guardar_trabajos()
            codigo = proceso.wait()
            trabajo["proceso"] = None
            trabajo["codigo"] = codigo
            trabajo["fin"] = time.time()
            if trabajo["cancelado"]:
                trabajo["estado"] = "Cancelado"
            elif codigo == 0:
                trabajo["estado"] = "Terminado"
            else:
                trabajo["estado"] = f"Falló (código {codigo})"
            guardar_trabajos()
        finally:
            with condicion_cola:
                id_cola_activo = None


def mostrar_cola():
    """Muestra los trabajos registrados en la cola."""
    trabajos_cola = [
        (id_trabajo, trabajo)
        for id_trabajo, trabajo in trabajos.items()
        if trabajo.get("es_cola")
    ]
    if not trabajos_cola:
        print("La cola está vacía.")
        return

    print(f"{'ID':<5} {'Estado':<12} {'Salida':<36} {'E-Level':<9} {'Tiempo':<20} Comando")
    tiempo_acumulado = 0
    ahora = time.time()
    for id_trabajo, trabajo in trabajos_cola:
        segundos = trabajo.get("segundos_solicitados", 0)
        inicio = trabajo.get("inicio")
        fin = trabajo.get("fin")
        codigo = trabajo.get("codigo")

        if inicio is not None:
            if fin is None:
                transcurrido = max(0, ahora - inicio)
                restante = max(0, segundos - transcurrido)
                tiempo_texto = f"{int(restante)}s restantes"
            else:
                duracion = max(0, fin - inicio)
                tiempo_texto = f"{duracion:.2f}s ejecución"
        else:
            tiempo_texto = ""

        if inicio is not None and fin is None:
            tiempo_acumulado = max(0, segundos - (ahora - inicio))
        elif inicio is None and trabajo.get("estado") == "En cola":
            tiempo_acumulado += segundos

        ruta_out, _ = rutas_salida(id_trabajo)
        codigo_texto = "" if codigo is None else ("-1" if codigo != 0 else "0")
        comando_mostrado = trabajo["comando"]
        if trabajo.get("es_cola") and comando_mostrado.startswith("queue "):
            comando_mostrado = comando_mostrado[len("queue "):]
        print(
            f"{id_trabajo:<5} {'':<12} {str(ruta_out.relative_to(Path(__file__).resolve().parent.parent)):<36} "
            f"{codigo_texto:<9} {tiempo_texto:<20} {comando_mostrado}"
        )


def mostrar_archivo(id_trabajo, indice, comando, descripcion):
    """Muestra el contenido de stdout (indice 0) o stderr (indice 1) de un trabajo."""
    ruta = rutas_salida(id_trabajo)[indice]
    if not ruta.exists():
        print(f"{comando}: el trabajo [{id_trabajo}] no tiene {descripcion} registrada")
        return
    contenido = ruta.read_text(encoding="utf-8", errors="replace")
    if contenido:
        print(contenido, end="" if contenido.endswith("\n") else "\n")
    else:
        print(f"{comando}: el trabajo [{id_trabajo}] no ha escrito nada en {descripcion}")


bloqueo_guardado = threading.Lock()


def _guardar_trabajos():
    """Guarda el historial y el siguiente ID sin escribir objetos Popen."""
    ARCHIVO_TRABAJOS.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "siguiente_id": siguiente_id,
        "trabajos": [
            {
                "id": id_trabajo,
                "comando": trabajo["comando"],
                "inicio": trabajo["inicio"],
                "fin": trabajo["fin"],
                "estado": trabajo["estado"],
                "codigo": trabajo["codigo"],
                "es_cola": trabajo.get("es_cola", False),
                "segundos_solicitados": trabajo.get("segundos_solicitados"),
                "momento_encolado": trabajo.get("momento_encolado"),
                "argumentos_cola": trabajo.get("argumentos_cola"),
            }
            for id_trabajo, trabajo in trabajos.items()
        ],
    }
    temporal = ARCHIVO_TRABAJOS.with_suffix(".tmp")
    try:
        with temporal.open("w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
        os.replace(temporal, ARCHIVO_TRABAJOS)
    finally:
        temporal.unlink(missing_ok=True)


def guardar_trabajos():
    """Evita que el hilo de la cola y el hilo principal escriban a la vez."""
    with bloqueo_guardado:
        _guardar_trabajos()


def cargar_trabajos():
    """Recupera el historial; una ejecución anterior ya no puede supervisarse."""
    if not ARCHIVO_TRABAJOS.exists():
        return {}, 1

    try:
        with ARCHIVO_TRABAJOS.open(encoding="utf-8") as archivo:
            datos = json.load(archivo)
        recuperados = {}
        for registro in datos["trabajos"]:
            id_trabajo = registro["id"]
            if not isinstance(id_trabajo, int) or id_trabajo < 1 or id_trabajo in recuperados:
                raise ValueError("ID inválido o repetido")
            recuperados[id_trabajo] = {
                "proceso": None,
                "comando": registro["comando"],
                "inicio": registro["inicio"],
                "fin": registro["fin"],
                "estado": registro["estado"],
                "codigo": registro["codigo"],
                "cancelado": registro["estado"] == "Cancelado",
                "es_cola": registro.get("es_cola", False),
                "segundos_solicitados": registro.get("segundos_solicitados"),
                "momento_encolado": registro.get("momento_encolado"),
                "argumentos_cola": (
                    " ".join(registro.get("argumentos_cola", []))
                    if isinstance(registro.get("argumentos_cola"), list)
                    else registro.get("argumentos_cola", registro.get("comando", "").partition(" ")[2])
                ),
            }
        proximo = datos["siguiente_id"]
        if not isinstance(proximo, int) or proximo < 1:
            raise ValueError("contador de ID inválido")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"No se pudo cargar {ARCHIVO_TRABAJOS}: {error}") from error

    return recuperados, max(proximo, max(recuperados, default=0) + 1)


trabajos, siguiente_id = cargar_trabajos()
if any(trabajo["estado"] == "En ejecución" for trabajo in trabajos.values()):
    for trabajo in trabajos.values():
        if trabajo["estado"] == "En ejecución":
            trabajo["estado"] = "Interrumpido"
            trabajo["fin"] = time.time()
    guardar_trabajos()


# Recupera trabajos queue que quedaron pendientes de una sesión anterior.
for _id, _trabajo in trabajos.items():
    if _trabajo.get("es_cola") and _trabajo.get("estado") == "En cola":
        cola_ids.append(_id)


def actualizar_trabajo(trabajo):
    """Registra el resultado cuando el proceso termina durante esta sesión."""
    proceso = trabajo["proceso"]
    if proceso is not None:
        codigo = proceso.poll()
        if codigo is not None:
            trabajo["proceso"] = None
            trabajo["codigo"] = codigo
            trabajo["fin"] = time.time()
            if trabajo["cancelado"]:
                trabajo["estado"] = "Cancelado"
            elif codigo == 0:
                trabajo["estado"] = "Terminado"
            else:
                trabajo["estado"] = f"Falló (código {codigo})"
            guardar_trabajos()
    return trabajo["estado"]


def estado_trabajo(trabajo):
    """Devuelve el estado actual de un trabajo como texto."""
    return actualizar_trabajo(trabajo)


def tiempo_trabajo(trabajo):
    """Evita que el tiempo de un trabajo terminado siga aumentando."""
    if trabajo["inicio"] is None:
        return 0  # Todavía en cola, o cancelado antes de arrancar.
    return int((trabajo["fin"] or time.time()) - trabajo["inicio"])


def codigo_salida_shell(codigo):
    """Presenta las terminaciones por señal como lo hace Bash en Linux."""
    return 128 - codigo if os.name == "posix" and codigo < 0 else codigo


def obtener_id(partes, comando):
    """Valida que el comando traiga un ID válido y que exista. Devuelve el ID o None."""
    if len(partes) == 1:
        print(f"{comando}: falta el ID del trabajo. Uso: {comando} <id>")
        return None
    if len(partes) != 2:
        print(f"{comando}: argumentos incorrectos. Uso: {comando} <id>")
        return None

    try:
        id_trabajo = int(partes[1])
    except ValueError:
        print(f"{comando}: el ID debe ser un número")
        return None

    if id_trabajo not in trabajos:
        print(f"{comando}: no existe el trabajo [{id_trabajo}]")
        return None

    return id_trabajo


hilo_cola = threading.Thread(target=procesar_cola, daemon=True)
hilo_cola.start()

while True:
    try:
        entrada = input("Q-umplidor> ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        break

    partes = entrada.split()

    if len(partes) == 0:
        continue

    if partes[0] == "help":
        if len(partes) != 1:
            print("help: no acepta argumentos. Uso: help")
            continue
        print("Comandos disponibles:")
        print("  sleep <segundos>    Ejecutar una espera en primer plano.")
        print("  sleep <segundos> &  Ejecutar un trabajo en segundo plano.")
        print("  estado <id>         Consultar el estado de un trabajo.")
        print("  listar              Listar los trabajos registrados.")
        print("  codigo <id>         Consultar el código de salida.")
        print("  cancelar <id>       Cancelar un trabajo en ejecución o en cola.")

        print("\n-------------------- AVANCE 02 --------------------\n")

        print("  queue <comando>     Ejecutar echo, sleep (&) o un programa en cola.")
        print("  queue               Mostrar la cola de trabajos.")
        print("  salida <id>         Mostrar la salida estándar (stdout).")
        print("  errores <id>        Mostrar la salida de error (stderr).")
        print("  help                Mostrar esta ayuda.")

    elif partes[0] == "queue":
        if len(partes) == 1:
            mostrar_cola()
            continue

        comando_cola = entrada.partition(" ")[2].strip()
        if not comando_cola:
            print("queue: debes indicar un comando después de queue")
            continue
        # Elimina un & final opcional para que cada trabajo termine antes de
        # iniciar el siguiente y la cola conserve su ejecución secuencial.
        if comando_cola.endswith("&"):
            comando_cola = comando_cola[:-1].rstrip()
        if not comando_cola:
            print("queue: debes indicar un comando después de queue")
            continue
        registrar_en_cola(comando_cola, comando_cola)

    elif partes[0] == "sleep":
        if len(partes) == 1 or partes == ["sleep", "&"]:
            print("sleep: faltan los segundos. Uso: sleep <segundos> o sleep <segundos> &")
            continue

        if len(partes) not in (2, 3) or (len(partes) == 3 and partes[2] != "&"):
            print("sleep: argumentos incorrectos. Uso: sleep <segundos> o sleep <segundos> &")
            continue
        try:
            segundos = int(partes[1])
            if segundos < 0:
                raise ValueError
        except ValueError:
            print("sleep: los segundos deben ser un entero no negativo")
            continue

        # Caso: sleep 10
        if len(partes) == 2:
            try:
                time.sleep(segundos)
            except (ValueError, OverflowError):
                print("sleep: invalid time interval")
            except KeyboardInterrupt:
                print()

        # Caso: sleep 10 &
        elif len(partes) == 3 and partes[2] == "&":
            try:
                proceso = lanzar_trabajo(siguiente_id, [
                    sys.executable,
                    "-c",
                    f"import time; time.sleep({segundos})"
                ])
                registrar_trabajo(proceso, entrada)
            except (ValueError, OverflowError):
                print("sleep: invalid time interval")

    # Ejecutar un programa cualquiera en segundo plano
    elif partes[0] == "ejecutar":
        try:
            argumentos = shlex.split(entrada)[1:]
        except ValueError:
            print("ejecutar: comillas sin cerrar")
            continue
        if not argumentos or argumentos[-1] != "&" or len(argumentos) == 1:
            print("ejecutar: uso: ejecutar <programa> [argumentos] &")
            continue
        try:
            proceso = lanzar_trabajo(siguiente_id, argumentos[:-1])
        except OSError as error:
            print(f"ejecutar: no se pudo iniciar '{argumentos[0]}': {error.strerror}")
            continue
        registrar_trabajo(proceso, entrada)

    # Mostrar stdout o stderr de un trabajo
    elif partes[0] in ("salida", "errores"):
        id_trabajo = obtener_id(partes, partes[0])
        if id_trabajo is not None:
            if partes[0] == "salida":
                mostrar_archivo(id_trabajo, 0, "salida", "la salida estándar")
            else:
                mostrar_archivo(id_trabajo, 1, "errores", "la salida de error")

    # Consulta el estado de un trabajo
    elif partes[0] == "estado":
        id_trabajo = obtener_id(partes, "estado")
        if id_trabajo is not None:
            trabajo = trabajos[id_trabajo]
            estado = estado_trabajo(trabajo)
            print(f"[{id_trabajo}] {trabajo['comando']} -> {estado} ({tiempo_trabajo(trabajo)}s)")

    # Listar los trabajos
    elif partes[0] == "listar":
        if len(partes) != 1:
            print("listar: no acepta argumentos. Uso: listar")
            continue
        if not trabajos:
            print("No hay trabajos registrados")
        else:
            print(f"{'ID':<4} {'ESTADO':<20} {'TIEMPO':<8} COMANDO")
            for id_trabajo, trabajo in trabajos.items():
                estado = estado_trabajo(trabajo)
                transcurrido = tiempo_trabajo(trabajo)
                print(
                    f"{id_trabajo:<4} {estado:<20} "
                    f"{transcurrido:<7}s {trabajo['comando']}"
                )

    # Obtener el código de salida de un trabajo
    elif partes[0] == "codigo":
        if len(partes) == 1:
            print("codigo: falta el ID del trabajo. Uso: codigo <id>")
        elif len(partes) != 2:
            print("codigo: argumentos incorrectos. Uso: codigo <id>")
        else:
            try:
                id_trabajo = int(partes[1])
                if id_trabajo not in trabajos:
                    print(f"codigo: no existe el trabajo [{id_trabajo}]")
                else:
                    trabajo = trabajos[id_trabajo]
                    estado = estado_trabajo(trabajo)
                    codigo = trabajo["codigo"]
                    if estado == "En ejecución":
                        print(f"codigo: el trabajo [{id_trabajo}] todavía está en ejecución, no tiene código de salida")
                    elif codigo is None:
                        print(f"codigo: no se conoce el código de salida del trabajo [{id_trabajo}] ({estado})")
                    else:
                        print(f"codigo: el trabajo [{id_trabajo}] terminó con código de salida {codigo_salida_shell(codigo)}")
            except ValueError:
                print("codigo: el ID debe ser un número")

    # Solicitud de cancelación
    elif partes[0] == "cancelar":
        id_trabajo = obtener_id(partes, "cancelar")
        if id_trabajo is not None:
            trabajo = trabajos[id_trabajo]

            # Trabajo en cola: se retira bajo el mismo candado que usa el hilo de la
            # cola, así nunca se cancela y se arranca al mismo tiempo (RF-10).
            with condicion_cola:
                en_cola = id_trabajo in cola_ids
                if en_cola:
                    cola_ids.remove(id_trabajo)
                    trabajo["cancelado"] = True
                    trabajo["estado"] = "Cancelado"
                    trabajo["fin"] = time.time()
            if en_cola:
                guardar_trabajos()
                print(f"Trabajo [{id_trabajo}] cancelado (estaba en cola, no llegó a ejecutarse)")
                continue

            estado = estado_trabajo(trabajo)
            proceso = trabajo["proceso"]

            if proceso is None and id_trabajo == id_cola_activo:
                print(f"cancelar: el trabajo [{id_trabajo}] está arrancando, intenta de nuevo en un momento")
            elif proceso is None:
                print(f"cancelar: el trabajo [{id_trabajo}] ya terminó ({estado})")
            else:
                trabajo["cancelado"] = True
                proceso.terminate()  # Envía SIGTERM
                try:
                    proceso.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proceso.kill()  # Envía SIGKILL si no respondió
                    proceso.wait()
                estado_trabajo(trabajo)
                print(f"Trabajo [{id_trabajo}] cancelado")

    # Manejar comandos inválidos sin terminar el servicio 
    else:
        print(f"{partes[0]}: comando no reconocido")


# Al salir, evitar que se inicien más trabajos de la cola y terminar procesos activos.
with condicion_cola:
    cola_cerrandose = True
    condicion_cola.notify_all()

for trabajo in trabajos.values():
    estado_trabajo(trabajo)
    proceso = trabajo["proceso"]
    if proceso is not None:
        proceso.terminate()
        try:
            proceso.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait()
        trabajo["proceso"] = None
        trabajo["estado"] = "Interrumpido"
        trabajo["codigo"] = proceso.returncode
        trabajo["fin"] = time.time()
guardar_trabajos()
