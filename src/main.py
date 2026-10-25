import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

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


def guardar_trabajos():
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
        print("  cancelar <id>       Cancelar un trabajo.")
        print("  ejecutar <cmd> &    Ejecutar un programa en segundo plano.")
        print("  salida <id>         Mostrar la salida estándar (stdout).")
        print("  errores <id>        Mostrar la salida de error (stderr).")
        print("  help                Mostrar esta ayuda.")

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
            estado = estado_trabajo(trabajo)
            proceso = trabajo["proceso"]

            if proceso is None:
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


# Al salir normalmente, termina los procesos que esta sesión aún supervisa.
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
