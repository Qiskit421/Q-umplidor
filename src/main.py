import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import threading
import atexit
from collections import deque
import event_log as ev

# Parte de Ruy (Avance 02): RF-05, RF-06 y RF-30
import concurrencia
import escalamiento
import estados
import recuperacion

if os.name == "nt":
    # Windows no tiene /proc ni grupos de procesos como Linux: se le pregunta
    # directamente con las funciones de kernel32 (ctypes viene con Python).
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

    class _LimiteBasico(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _LimiteExtendido(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _LimiteBasico), ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _Contabilidad(ctypes.Structure):
        _fields_ = [
            ("Tiempos", ctypes.c_int64 * 4), ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD), ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, wintypes.LPDWORD]
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE

    class GrupoDeProcesos:
        """Job Object de Windows con el proceso de un trabajo y todo lo que lance.

        Se puede contar y terminar completo, y si Q-umplidor se cierra de golpe,
        Windows termina el grupo solo (KILL_ON_JOB_CLOSE): no quedan huérfanos.
        """

        def __init__(self, proceso):
            self._manejador = kernel32.CreateJobObjectW(None, None)
            limites = _LimiteExtendido()
            limites.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            kernel32.SetInformationJobObject(self._manejador, 9, ctypes.byref(limites), ctypes.sizeof(limites))
            kernel32.AssignProcessToJobObject(self._manejador, int(proceso._handle))

        def activos(self):
            """Cuántos procesos del grupo siguen vivos."""
            info = _Contabilidad()
            ok = self._manejador and kernel32.QueryInformationJobObject(
                self._manejador, 1, ctypes.byref(info), ctypes.sizeof(info), None)
            return info.ActiveProcesses if ok else 0

        def terminar(self):
            """Termina todos los procesos del grupo."""
            if self._manejador:
                kernel32.TerminateJobObject(self._manejador, 1)

        def cerrar(self):
            """Libera el manejador del grupo."""
            if self._manejador:
                kernel32.CloseHandle(self._manejador)
                self._manejador = None

    def termino_sin_recolectar(proceso):
        """True si el proceso ya terminó pero Q-umplidor todavía no lo recolecta."""
        return kernel32.WaitForSingleObject(int(proceso._handle), 0) == 0

    def archivo_abierto(ruta):
        """True si algún proceso tiene el archivo abierto.

        Se intenta abrir en modo exclusivo: Windows lo impide (error 32) mientras
        otro lo tenga abierto. El archivo no se modifica.
        """
        manejador = kernel32.CreateFileW(str(ruta), 0x80000000, 0, None, 3, 0, None)
        if manejador == INVALID_HANDLE_VALUE:
            return ctypes.get_last_error() == 32
        kernel32.CloseHandle(manejador)
        return False


def procesos_linux(carpeta_datos):
    """Lee de /proc los procesos: lista de (pid, ppid, estado, id de trabajo o None).

    El id sale de la variable QUMPLIDOR_TRABAJO que heredan los procesos de cada
    trabajo ("3" fuera de la cola, "cola-3" en la cola); solo cuenta si
    QUMPLIDOR_DATOS es esta misma carpeta de datos.
    """
    datos = f"QUMPLIDOR_DATOS={carpeta_datos}".encode()
    encontrados = []
    for carpeta in Path("/proc").iterdir():
        if not carpeta.name.isdigit():
            continue
        try:
            stat = (carpeta / "stat").read_text()
        except OSError:
            continue  # terminó mientras se revisaba
        try:
            variables = (carpeta / "environ").read_bytes().split(b"\0")
        except OSError:
            variables = []  # un zombi o un proceso de otro usuario no deja leerlas
        # El nombre del programa va entre paréntesis y puede tener espacios.
        campos = stat[stat.rfind(")") + 2:].split()
        id_trabajo = None
        if datos in variables:
            for variable in variables:
                if variable.startswith(b"QUMPLIDOR_TRABAJO="):
                    id_trabajo = variable.split(b"=", 1)[1].decode()
        encontrados.append((int(carpeta.name), int(campos[1]), campos[0], id_trabajo))
    return encontrados


def archivos_abiertos_linux(carpeta):
    """Nombres de los archivos dentro de carpeta que Q-umplidor tiene abiertos."""
    abiertos = []
    for descriptor in Path("/proc/self/fd").iterdir():
        try:
            destino = os.readlink(descriptor)
        except OSError:
            continue
        if destino.startswith(str(carpeta)):
            abiertos.append(Path(destino).name)
    return abiertos


ARCHIVO_TRABAJOS = Path(__file__).resolve().parent.parent / "data" / "trabajos.json"
CARPETA_SALIDAS = ARCHIVO_TRABAJOS.parent / "salidas"
BITACORA = ev.EventLog(ARCHIVO_TRABAJOS.parent / "events.jsonl")
politica = escalamiento.leer_politica()  # RF-30: gracia entre SIGTERM y SIGKILL, tiempo máximo

def marca_trabajo(id_trabajo, de_cola):
    """Nombre único de un trabajo: la cola y lo de afuera tienen su propia numeración."""
    return f"cola-{id_trabajo}" if de_cola else str(id_trabajo)


def opciones_hijo(id_trabajo, de_cola=False):
    """Opciones de Popen comunes a todos los trabajos.

    Cada trabajo corre en su propio grupo de procesos. En Linux/WSL así la señal
    de cancelar o salir llega también a los procesos que el trabajo haya lanzado
    (por ejemplo, el sleep dentro de "queue sleep 100; echo hola"). En los dos
    sistemas, un Ctrl+C en la consola ya no llega directo a los trabajos:
    Q-umplidor los termina él mismo al salir.
    Las variables QUMPLIDOR_* marcan a qué trabajo pertenece cada proceso, para
    que el comando recursos pueda encontrarlos en Linux/WSL.
    """
    opciones = {
        "env": {
            **os.environ,
            "QUMPLIDOR_TRABAJO": marca_trabajo(id_trabajo, de_cola),
            "QUMPLIDOR_DATOS": str(ARCHIVO_TRABAJOS.parent),
        }
    }
    if os.name == "posix":
        opciones["start_new_session"] = True
    else:
        opciones["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return opciones


def enviar_senal(proceso, forzar=False):
    """Envía SIGTERM (o SIGKILL si forzar) al grupo completo del trabajo."""
    if os.name == "posix":
        try:
            os.killpg(proceso.pid, signal.SIGKILL if forzar else signal.SIGTERM)
        except ProcessLookupError:
            pass  # el grupo ya no tiene procesos
    else:
        # En Windows no hay señales: se termina todo el grupo (Job Object) de golpe.
        grupo = getattr(proceso, "grupo_windows", None)
        if grupo is not None:
            grupo.terminar()
        proceso.terminate()


def agrupar(proceso):
    """En Windows mete al trabajo recién lanzado en su propio grupo de procesos."""
    if os.name == "nt":
        proceso.grupo_windows = GrupoDeProcesos(proceso)
    return proceso


escalamiento.usar_envio_de_senales(enviar_senal)


def terminar_proceso(proceso):
    """Termina el trabajo y todo su grupo, y recolecta al proceso hijo (RF-30).

    Política de escalamiento: SIGTERM al grupo -> gracia -> SIGKILL.
    Devuelve "SIGTERM" o "SIGKILL" según la señal que lo detuvo (None si ya había terminado).
    """
    senal = escalamiento.terminar_con_escalamiento(proceso, politica.gracia)
    # Si algún proceso del grupo ignoró SIGTERM y sigue vivo, no lo dejamos huérfano.
    enviar_senal(proceso, forzar=True)
    return senal


def rutas_salida(id_trabajo, de_cola=False):
    """Cada trabajo tiene dos archivos: uno para stdout y otro para stderr.

    Los de la cola llevan el prefijo "cola-" porque su numeración es aparte.
    """
    nombre = marca_trabajo(id_trabajo, de_cola)
    return (
        CARPETA_SALIDAS / f"{nombre}.out",
        CARPETA_SALIDAS / f"{nombre}.err",
    )


def lanzar_trabajo(id_trabajo, argumentos):
    """Lanza un trabajo de afuera (Avance 01) en segundo plano.

    Todo lo del Avance 02 (captura de salidas, grupos de procesos, bitácora,
    duplicados, escalamiento, persistencia) es solo de la cola.
    """
    return subprocess.Popen(
        argumentos,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def registrar_trabajo(proceso, entrada):
    """Guarda el trabajo de afuera recién lanzado (solo en memoria) y muestra su ID."""
    global siguiente_id
    trabajos[siguiente_id] = {
        "id": siguiente_id,
        "proceso": proceso,
        "comando": entrada,
        "inicio": time.time(),
        "fin": None,
        "estado": "En ejecución",
        "codigo": None,
        "cancelado": False,
    }
    # Espera al proceso para anotar la hora real en que termina; si no, el fin
    # quedaría en el momento en que alguien lo consulta con listar o estado.
    threading.Thread(
        target=lambda t=trabajos[siguiente_id], i=siguiente_id: finalizar_trabajo(i, t, proceso.wait()),
        daemon=True,
    ).start()
    print(f"ID: [{siguiente_id}]")
    siguiente_id += 1


def terminar_trabajo_afuera(trabajo):
    """Cancela un trabajo de afuera como en el Avance 01: terminate y, si no responde, kill."""
    proceso = trabajo["proceso"]
    proceso.terminate()
    try:
        proceso.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proceso.kill()
        proceso.wait()


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
ids_arrancando = set()  # trabajos de la cola que ya ocupan lugar pero aún no tienen proceso (RF-05)
hilos_de_cola = []      # un hilo por trabajo de la cola; el cierre espera a que terminen


def registrar_en_cola(comando, entrada):
    """Registra cualquier comando pendiente y lo agrega al final de la cola."""
    global siguiente_id_cola
    with condicion_cola:
        en_espera = len(cola_ids)
    if en_espera >= CAPACIDAD_COLA:
        # Rechazo explícito (RF-25, RNF-29): no se registra, no consume ID y no bloquea.
        BITACORA.record(ev.JOB_REJECTED, comando=comando, motivo="cola llena")
        print(f"queue: cola llena ({en_espera}/{CAPACIDAD_COLA} en espera), trabajo rechazado. "
              "Intenta de nuevo cuando avance la cola.")
        return
    id_trabajo = siguiente_id_cola
    duplicado = buscar_duplicado(entrada, de_cola=True)
    extra = {} if duplicado is None else {"duplicado_de": duplicado}
    # Los archivos de salida se crean hasta que el trabajo arranca; si se cancela
    # estando en cola no deja archivos vacíos.
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
    trabajos_cola[id_trabajo] = {
        "id": id_trabajo,
        "proceso": None, "comando": entrada, "argumentos_cola": comando,
        "inicio": None, "fin": None, "estado": "En cola", "codigo": None,
        "cancelado": False, "es_cola": True,
        "segundos_solicitados": segundos,
        "momento_encolado": time.time(),
    }
    siguiente_id_cola += 1
    guardar_trabajos()
    BITACORA.record(ev.JOB_SUBMITTED, id_trabajo, comando=comando, **extra)

    with condicion_cola:
        cola_ids.append(id_trabajo)
        condicion_cola.notify()
    print(f"ID: [{id_trabajo}] agregado a la cola")
    if duplicado is not None:
        print(f"aviso: ya hay un trabajo activo con el mismo comando ([{duplicado}])")


def contar_activos():
    """Trabajos de la cola que ocupan lugar: procesos vivos + los que está arrancando (RF-05).

    Los trabajos fuera de la cola (sleep N &, ejecutar) no cuentan para el límite.
    """
    vivos = sum(
        1 for trabajo in list(trabajos_cola.values())
        if trabajo.get("proceso") is not None and trabajo["proceso"].poll() is None
    )
    arrancando = sum(
        1 for id_trabajo in list(ids_arrancando)
        if trabajos_cola.get(id_trabajo, {}).get("proceso") is None
    )
    return vivos + arrancando


def despachar_cola():
    """Saca trabajos de la cola en orden de llegada mientras haya lugar (RF-05).

    Arranca tantos como permita el límite de concurrencia; cada uno corre en su
    propio hilo, que solo espera a que su proceso termine.
    """
    while True:
        with condicion_cola:
            while True:
                if cola_cerrandose:
                    return
                if cola_ids and control_concurrencia.hay_espacio():
                    break
                # El timeout revisa de nuevo aunque nadie avise, por ejemplo
                # cuando termina un trabajo lanzado con "&".
                condicion_cola.wait(timeout=0.2)
            id_trabajo = cola_ids.popleft()
            trabajo = trabajos_cola.get(id_trabajo)
            if trabajo is None or trabajo.get("cancelado"):
                continue
            # Ocupa su lugar desde ya, antes de que exista el proceso.
            ids_arrancando.add(id_trabajo)
        hilo = threading.Thread(target=ejecutar_de_cola, args=(id_trabajo, trabajo), daemon=True)
        hilos_de_cola.append(hilo)
        hilo.start()


def ejecutar_de_cola(id_trabajo, trabajo):
    """Ejecuta un trabajo de la cola y registra su resultado."""
    try:
        with bloqueo_trabajos:
            if trabajo["cancelado"] or cola_cerrandose:
                return  # lo cancelaron, o el programa se está cerrando
            trabajo["inicio"] = time.time()
            trabajo["estado"] = "En ejecución"
        guardar_trabajos()
        # Los sleep de la cola se ejecutan con Python para que funcionen
        # tanto en Windows como en Linux/WSL. Los demás comandos usan el shell.
        CARPETA_SALIDAS.mkdir(parents=True, exist_ok=True)
        ruta_out, ruta_err = rutas_salida(id_trabajo, de_cola=True)
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
                    **opciones_hijo(id_trabajo, de_cola=True),
                )
            else:
                proceso = subprocess.Popen(
                    comando,
                    shell=True,
                    executable="/bin/bash" if os.name == "posix" else None,
                    stdin=subprocess.DEVNULL,
                    stdout=salida,
                    stderr=errores,
                    **opciones_hijo(id_trabajo, de_cola=True),
                )
            agrupar(proceso)

        with bloqueo_trabajos:
            trabajo["proceso"] = proceso
            trabajo["huella"] = recuperacion.huella_proceso(proceso.pid)  # ADR-0006
            if cola_cerrandose:
                trabajo["interrumpido"] = True  # el programa se está cerrando
            detener_ya = trabajo["cancelado"] or cola_cerrandose
        if detener_ya:
            terminar_proceso(proceso)  # lo cancelaron justo al iniciar
        guardar_trabajos()
        BITACORA.record(ev.JOB_STARTED, id_trabajo, pid=proceso.pid, comando=comando)
        codigo = proceso.wait()
        finalizar_trabajo(id_trabajo, trabajo, codigo)
    finally:
        with condicion_cola:
            ids_arrancando.discard(id_trabajo)  # ya cuenta como proceso vivo, o no arrancó
            condicion_cola.notify_all()          # se liberó un lugar


def mostrar_cola():
    """Muestra los trabajos registrados en la cola."""
    if not trabajos_cola:
        print("La cola está vacía.")
        return

    print(f"{'ID':<5} {'Estado':<12} {'Salida':<36} {'E-Level':<9} {'Tiempo':<20} Comando")
    tiempo_acumulado = 0
    ahora = time.time()
    for id_trabajo, trabajo in list(trabajos_cola.items()):
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

        ruta_out, _ = rutas_salida(id_trabajo, de_cola=True)
        codigo_texto = "" if codigo is None else ("-1" if codigo != 0 else "0")
        comando_mostrado = trabajo["comando"]
        if trabajo.get("es_cola") and comando_mostrado.startswith("queue "):
            comando_mostrado = comando_mostrado[len("queue "):]
        print(
            f"{id_trabajo:<5} {estados.estado_cliente(trabajo['estado']):<12} {str(ruta_out.relative_to(Path(__file__).resolve().parent.parent)):<36} "
            f"{codigo_texto:<9} {tiempo_texto:<20} {comando_mostrado}"
        )


def limpiar_cola_terminados():
    """queue clear: borra los trabajos terminados de la cola, sus .out/.err y trabajos.json.

    Los trabajos en cola o en ejecución se conservan porque siguen en uso.
    Si la cola queda vacía, trabajos.json se borra y no se vuelve a crear hasta
    el siguiente trabajo de la cola, así que sus IDs empiezan otra vez en 1.
    Los trabajos de afuera (Avance 01) no se tocan. La bitácora se conserva.
    """
    global siguiente_id_cola
    quitados, borrados = [], []
    with bloqueo_trabajos:
        for id_trabajo, trabajo in list(trabajos_cola.items()):
            estado_trabajo(trabajo)  # refresca si acaba de terminar
            if trabajo["fin"] is None:
                continue
            grupo = trabajo.get("grupo_windows")
            if grupo is not None:
                grupo.terminar()
                grupo.cerrar()
            for ruta in rutas_salida(id_trabajo, de_cola=True):
                if ruta.exists():
                    ruta.unlink(missing_ok=True)
                    borrados.append(ruta.name)
            del trabajos_cola[id_trabajo]
            quitados.append(id_trabajo)
        # Salidas que ya no pertenecen a ningún trabajo (por ejemplo, de una versión anterior).
        for ruta in salidas_huerfanas():
            ruta.unlink(missing_ok=True)
            borrados.append(ruta.name)
        json_borrado = False
        if not trabajos_cola:
            json_borrado = ARCHIVO_TRABAJOS.exists()
            siguiente_id_cola = 1
            with bloqueo_guardado:
                ARCHIVO_TRABAJOS.unlink(missing_ok=True)
        elif quitados:
            guardar_trabajos()
    if quitados or borrados or json_borrado:
        BITACORA.record(ev.OUTPUT_FILES_CLEARED, trabajos=quitados, archivos=sorted(borrados))
        print("queue clear: se borraron los trabajos terminados de la cola y sus salidas")
    else:
        print("queue clear: no hay trabajos terminados en la cola")


def mostrar_archivo(id_trabajo, indice, comando, descripcion):
    """Muestra el contenido de stdout (indice 0) o stderr (indice 1) de un trabajo de la cola."""
    ruta = rutas_salida(id_trabajo, de_cola=True)[indice]
    if not ruta.exists():
        print(f"{comando}: el trabajo [{id_trabajo}] no tiene {descripcion} registrada")
        return
    contenido = ruta.read_text(encoding="utf-8", errors="replace")
    if contenido:
        print(contenido, end="" if contenido.endswith("\n") else "\n")
    else:
        print(f"{comando}: el trabajo [{id_trabajo}] no ha escrito nada en {descripcion}")


bloqueo_guardado = threading.Lock()
bloqueo_trabajos = threading.RLock()

def _registro(id_trabajo, trabajo):
    """Datos de un trabajo que se guardan en el JSON (sin objetos Popen)."""
    return {
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
        "motivo_fin": trabajo.get("motivo_fin"),
        "senal_final": trabajo.get("senal_final"),
        "huella": trabajo.get("huella"),
    }


def _escribir_json(ruta, datos):
    """Escribe el JSON completo de una vez para no dejarlo a medias."""
    temporal = ruta.with_suffix(".tmp")
    try:
        with temporal.open("w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
        # En Windows el reemplazo falla si otro programa tiene el archivo
        # abierto en ese instante: se reintenta un momento.
        for intento in range(20):
            try:
                os.replace(temporal, ruta)
                break
            except PermissionError:
                if intento == 19:
                    raise
                time.sleep(0.05)
    finally:
        temporal.unlink(missing_ok=True)


def _guardar_trabajos():
    """Guarda los trabajos de la cola y su siguiente ID sin escribir objetos Popen.

    Solo la cola (Avance 02) tiene persistencia: los trabajos de afuera viven
    mientras el programa está abierto. Sin trabajos en la cola no hay nada que
    guardar, así trabajos.json no reaparece al salir después de queue clear.
    """
    if not trabajos_cola:
        return
    ARCHIVO_TRABAJOS.parent.mkdir(parents=True, exist_ok=True)
    _escribir_json(ARCHIVO_TRABAJOS, {
        "siguiente_id": siguiente_id_cola,
        # list(): con varios trabajos de la cola, otro hilo puede agregar
        # un trabajo mientras se guarda.
        "trabajos": [_registro(i, trabajo) for i, trabajo in list(trabajos_cola.items())],
    })


def guardar_trabajos():
    """Evita que el hilo de la cola y el hilo principal escriban a la vez.

    Si aun así no se puede guardar, avisa en lugar de cerrar el programa.
    """
    with bloqueo_guardado:
        try:
            _guardar_trabajos()
        except OSError as error:
            print(f"\n[aviso] no se pudo guardar el historial: {error}")


def cargar_trabajos():
    """Recupera el historial; una ejecución anterior ya no puede supervisarse.

    Solo se recuperan los trabajos de la cola; los de afuera empiezan vacíos
    y su numeración vuelve a 1 en cada sesión.
    """
    afuera, cola = {}, {}
    ruta = ARCHIVO_TRABAJOS
    if not ruta.exists():
        return afuera, cola, 1, 1
    try:
        with ruta.open(encoding="utf-8") as archivo:
            datos = json.load(archivo)
        for registro in datos["trabajos"]:
            id_trabajo = registro["id"]
            if not registro.get("es_cola", False):
                continue  # de una versión anterior: lo de afuera no se recupera
            recuperados = cola
            if not isinstance(id_trabajo, int) or id_trabajo < 1 or id_trabajo in recuperados:
                raise ValueError("ID inválido o repetido")
            recuperados[id_trabajo] = {
                "id": id_trabajo,
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
                "motivo_fin": registro.get("motivo_fin"),
                "senal_final": registro.get("senal_final"),
                "huella": registro.get("huella"),
                "argumentos_cola": (
                    " ".join(registro.get("argumentos_cola", []))
                    if isinstance(registro.get("argumentos_cola"), list)
                    else registro.get("argumentos_cola", registro.get("comando", "").partition(" ")[2])
                ),
            }
        # Versiones anteriores guardaban el de la cola aparte, en "siguiente_id_cola".
        proximo_cola = datos.get("siguiente_id_cola", datos["siguiente_id"])
        if not isinstance(proximo_cola, int) or proximo_cola < 1:
            raise ValueError("contador de ID inválido")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"No se pudo cargar {ruta}: {error}") from error
    return afuera, cola, 1, max(proximo_cola, max(cola, default=0) + 1)


trabajos, trabajos_cola, siguiente_id, siguiente_id_cola = cargar_trabajos()


def todos_los_trabajos():
    """Los trabajos de los dos lados, para lo que revisa el programa completo."""
    return list(trabajos.values()) + list(trabajos_cola.values())


for _lado in (trabajos, trabajos_cola):
    if any(trabajo["estado"] == "En ejecución" for trabajo in _lado.values()):
        # Si la sesión anterior se cayó (kill -9), sus trabajos pueden seguir vivos:
        # se detienen antes de marcarlos Interrumpido (ADR-0006).
        for mensaje in recuperacion.recuperar_trabajos(_lado, politica.gracia):
            print(mensaje)
        guardar_trabajos()


def salidas_huerfanas():
    """Archivos .out/.err que no pertenecen a ningún trabajo del historial."""
    if not CARPETA_SALIDAS.exists():
        return []
    huerfanas = []
    for ruta in CARPETA_SALIDAS.iterdir():
        if ruta.suffix not in (".out", ".err"):
            continue
        nombre, lado = ruta.stem, trabajos
        if nombre.startswith("cola-"):
            nombre, lado = nombre[len("cola-"):], trabajos_cola
        if not (nombre.isdigit() and int(nombre) in lado):
            huerfanas.append(ruta)
    return huerfanas


def limpiar_salidas_huerfanas():
    """Borra los .out/.err que no pertenecen a ningún trabajo del historial.

    Pueden quedar si el programa se cerró de golpe entre crear los archivos y
    guardar el trabajo, o si se borró trabajos.json.
    """
    ARCHIVO_TRABAJOS.with_suffix(".tmp").unlink(missing_ok=True)  # guardado interrumpido
    borrados = []
    for ruta in salidas_huerfanas():
        ruta.unlink(missing_ok=True)
        borrados.append(ruta.name)
    if borrados:
        BITACORA.record(ev.ORPHAN_FILES_REMOVED, archivos=sorted(borrados))


limpiar_salidas_huerfanas()
BITACORA.record(ev.SYSTEM_STARTED, trabajos_previos=len(trabajos) + len(trabajos_cola))
atexit.register(lambda: BITACORA.record(ev.SYSTEM_STOPPED))


# Recupera trabajos queue que quedaron pendientes de una sesión anterior.
for _id, _trabajo in trabajos_cola.items():
    if _trabajo.get("estado") == "En cola":
        cola_ids.append(_id)

def finalizar_trabajo(id_trabajo, trabajo, codigo):
    """Cierra un trabajo una sola vez, aunque dos hilos lo detecten a la vez."""
    with bloqueo_trabajos:
        if trabajo["fin"] is not None:
            return False  # otro hilo ya lo cerró
        if not trabajo.get("es_cola"):
            # Afuera (Avance 01): sin bitácora ni persistencia, como en el Avance 01.
            trabajo["proceso"] = None
            trabajo["codigo"] = codigo
            trabajo["fin"] = time.time()
            if trabajo.get("interrumpido"):
                trabajo["estado"] = "Interrumpido"
            elif trabajo["cancelado"]:
                trabajo["estado"] = "Cancelado"
            elif codigo == 0:
                trabajo["estado"] = "Terminado"
            else:
                trabajo["estado"] = f"Falló (código {codigo})"
            return True
        if trabajo["proceso"] is not None:
            # Si el trabajo dejó procesos en segundo plano (p. ej. "sleep 100 & echo hola"),
            # se terminan con él para que no queden huérfanos.
            enviar_senal(trabajo["proceso"], forzar=True)
            # En Windows el grupo se conserva hasta confirmar que quedó vacío
            # (lo cierra el recolector); así recursos puede revisarlo.
            trabajo["grupo_windows"] = getattr(trabajo["proceso"], "grupo_windows", None)
        trabajo["proceso"] = None
        trabajo["codigo"] = codigo
        trabajo["fin"] = time.time()
        if trabajo.get("interrumpido"):
            trabajo["estado"] = "Interrumpido"
            evento = ev.JOB_INTERRUPTED
        else:
            # Una sola regla para todos los caminos (RF-06, RF-30).
            trabajo["estado"] = estados.estado_final(trabajo, codigo)
            evento = ev.JOB_CANCELLED if trabajo["estado"] == "Cancelado" else ev.JOB_FINISHED
        guardar_trabajos()
        extra = {"motivo": trabajo["motivo_fin"]} if trabajo.get("motivo_fin") else {}
        BITACORA.record(evento, id_trabajo, estado=trabajo["estado"], exit_code=codigo, **extra)
        return True


def actualizar_trabajo(trabajo):
    """Registra el resultado cuando el proceso termina durante esta sesión."""
    proceso = trabajo["proceso"]
    if proceso is not None:
        codigo = proceso.poll()
        if codigo is not None:
            finalizar_trabajo(trabajo.get("id"), trabajo, codigo)
    return trabajo["estado"]

def normalizar_comando(texto):
    """Compara comandos sin importar espacios extra ni un & final."""
    texto = texto.strip()
    if texto.endswith("&"):
        texto = texto[:-1]
    return " ".join(texto.split())


def buscar_duplicado(comando, de_cola):
    """Devuelve el ID de un trabajo activo con el mismo comando, o None.

    Solo compara dentro del mismo lado: la cola o fuera de ella.
    """
    buscado = normalizar_comando(comando)
    with bloqueo_trabajos:
        for id_existente, existente in list((trabajos_cola if de_cola else trabajos).items()):
            estado_trabajo(existente)  # refresca si ya terminó
            if (
                existente["fin"] is None
                and existente["estado"] in ("En cola", "En ejecución")
                and normalizar_comando(existente["comando"]) == buscado
            ):
                return id_existente
    return None


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


def revisar_recursos_windows():
    """Igual que revisar_recursos_linux, pero preguntando a Windows."""
    vivos, zombis, huerfanos, abiertos = [], [], [], []
    for id_trabajo, trabajo in list(trabajos_cola.items()):
        proceso = trabajo["proceso"]
        if proceso is not None:
            if termino_sin_recolectar(proceso):
                zombis.append(id_trabajo)  # terminó y nadie lo ha recolectado
            else:
                grupo = getattr(proceso, "grupo_windows", None)
                vivos += [id_trabajo] * (grupo.activos() if grupo else 1)
        elif trabajo.get("grupo_windows") is not None:
            huerfanos += [id_trabajo] * trabajo["grupo_windows"].activos()

    # Archivos que nadie debería tener abiertos: las salidas de los trabajos de la
    # cola que no están corriendo (lo de afuera no guarda salidas). trabajos.json y
    # events.jsonl no se revisan: abrirlos para revisarlos impediría que otro hilo
    # los guarde en ese mismo instante.
    revisar = []
    for id_trabajo, trabajo in list(trabajos_cola.items()):
        if trabajo["proceso"] is None:
            revisar += list(rutas_salida(id_trabajo, de_cola=True))
    revisar += salidas_huerfanas()
    for ruta in revisar:
        if ruta.exists() and archivo_abierto(ruta):
            abiertos.append(ruta.name)
    return vivos, zombis, huerfanos, abiertos


def revisar_recursos_linux():
    """Lee de /proc qué procesos y archivos de Q-umplidor siguen en uso."""
    por_pid = {
        trabajo["proceso"].pid: id_trabajo
        for id_trabajo, trabajo in list(trabajos_cola.items())
        if trabajo["proceso"] is not None
    }
    vivos, zombis, huerfanos = [], [], []
    for pid, ppid, estado, marca in procesos_linux(ARCHIVO_TRABAJOS.parent):
        if estado == "Z":
            # Un zombi ya no tiene variables; se identifica por ser hijo de Q-umplidor.
            if ppid == os.getpid() and pid in por_pid:
                zombis.append(por_pid[pid])
            continue
        if marca is None or not marca.startswith("cola-"):
            continue
        id_trabajo = int(marca[len("cola-"):])
        trabajo = trabajos_cola.get(id_trabajo)
        if trabajo is not None and trabajo["fin"] is None:
            vivos.append(id_trabajo)
        else:
            huerfanos.append(id_trabajo)  # su trabajo ya terminó y el proceso sigue vivo
    abiertos = archivos_abiertos_linux(ARCHIVO_TRABAJOS.parent)
    return vivos, zombis, huerfanos, abiertos


def mostrar_recursos():
    """Revisa en el sistema qué procesos y archivos de la cola siguen en uso.

    No recolecta nada antes de revisar: si hay zombis, es porque el recolector
    no hizo su trabajo, y deben verse.
    """
    if os.name == "nt":
        vivos, zombis, huerfanos, abiertos = revisar_recursos_windows()
    else:
        vivos, zombis, huerfanos, abiertos = revisar_recursos_linux()
    sin_trabajo = sorted(ruta.name for ruta in salidas_huerfanas())

    def detalle_ids(ids):
        ids = sorted({i for i in ids if i is not None})
        return f"   (trabajos: {', '.join(f'[{i}]' for i in ids)})" if ids else ""

    def detalle_archivos(nombres):
        return f"   ({', '.join(sorted(nombres))})" if nombres else ""

    # Cuántos trabajos hay detrás de los números, para que un 0 se lea como "0 de N".
    por_estado = {}
    for trabajo in list(trabajos_cola.values()):
        estado = trabajo["estado"]
        grupo = "fallidos" if estado.startswith("Falló") else {
            "En cola": "en cola", "En ejecución": "en ejecución", "Terminado": "terminados",
            "Cancelado": "cancelados", "Interrumpido": "interrumpidos",
        }.get(estado, estado)
        por_estado[grupo] = por_estado.get(grupo, 0) + 1
    if por_estado:
        detalle = ", ".join(f"{grupo}: {cantidad}" for grupo, cantidad in por_estado.items())
    else:
        detalle = "todavía no se ha lanzado ninguno"

    print(f"Trabajos revisados .......... {len(trabajos_cola)}   ({detalle})")
    print(f"Procesos hijos vivos ........ {len(vivos)}{detalle_ids(vivos)}")
    print(f"Procesos zombi .............. {len(zombis)}{detalle_ids(zombis)}")
    print(f"Procesos huérfanos .......... {len(huerfanos)}{detalle_ids(huerfanos)}")
    print(f"Archivos abiertos ........... {len(abiertos)}{detalle_archivos(abiertos)}")
    print(f"Archivos de salida huérfanos  {len(sin_trabajo)}{detalle_archivos(sin_trabajo)}")


def obtener_id(partes, comando, de_cola):
    """Valida que el comando traiga un ID válido y que exista. Devuelve el ID o None.

    Los comandos de la cola (Avance 02) solo ven trabajos de la cola, y los del
    Avance 01 solo ven los que se lanzaron fuera de ella.
    """
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

    if id_trabajo not in (trabajos_cola if de_cola else trabajos):
        donde = " en la cola" if de_cola else ""
        print(f"{comando}: no existe el trabajo [{id_trabajo}]{donde}")
        return None

    return id_trabajo


def trabajos_en_ejecucion():
    """Trabajos de la cola vivos: el tiempo máximo (RF-30) es solo de la cola."""
    return [
        (id_trabajo, trabajo)
        for id_trabajo, trabajo in list(trabajos_cola.items())
        if trabajo.get("proceso") is not None and trabajo["proceso"].poll() is None
    ]


def al_detener_por_tiempo(id_trabajo, trabajo, senal):
    estado_trabajo(trabajo)
    detalle = "forzado con SIGKILL" if senal == "SIGKILL" else "terminó con SIGTERM"
    print(f"\n[aviso] Trabajo [{id_trabajo}] de la cola superó el tiempo máximo y se detuvo ({detalle})")


control_concurrencia = concurrencia.ControlConcurrencia(
    concurrencia.leer_limite_concurrencia(), contar_activos
)


def avisar_despachador():
    with condicion_cola:
        condicion_cola.notify_all()


hilo_cola = threading.Thread(target=despachar_cola, daemon=True)
hilo_cola.start()
escalamiento.iniciar_vigilante(
    politica, trabajos_en_ejecucion, al_detener_por_tiempo, lambda: cola_cerrandose
)

cerrando = threading.Event()


def recolectar_terminados():
    """Recoge cada medio segundo los trabajos de la cola que terminaron para que no queden zombis.

    Sin esto, un hijo terminado sigue como <defunct> hasta que alguien consulta
    su estado. Es parte de la liberación de recursos del Avance 02: lo de afuera
    se actualiza como en el Avance 01, al consultarlo.
    """
    while not cerrando.wait(0.5):
        for trabajo in list(trabajos_cola.values()):
            if trabajo["proceso"] is not None:
                actualizar_trabajo(trabajo)
            grupo = trabajo.get("grupo_windows")
            if trabajo["fin"] is not None and grupo is not None and grupo.activos() == 0:
                grupo.cerrar()  # Windows: libera el grupo del trabajo ya terminado
                trabajo["grupo_windows"] = None


hilo_recolector = threading.Thread(target=recolectar_terminados, daemon=True)
hilo_recolector.start()

def barrido_final():
    """Último recurso: mata y recolecta lo que haya quedado de Q-umplidor."""
    if os.name == "nt":
        for trabajo in todos_los_trabajos():
            grupo = trabajo.get("grupo_windows")
            if grupo is not None:
                grupo.terminar()
                limite = time.time() + 2
                while grupo.activos() > 0 and time.time() < limite:
                    time.sleep(0.05)
                grupo.cerrar()
                trabajo["grupo_windows"] = None
        return

    # Linux/WSL: los procesos que escaparon de su grupo (setsid, demonios)
    # siguen llevando QUMPLIDOR_TRABAJO en su entorno, así que se encuentran por ahí.
    limite = time.time() + 2
    while True:
        sobrevivientes = [
            pid
            for pid, _ppid, _estado, id_trabajo in procesos_linux(ARCHIVO_TRABAJOS.parent)
            if id_trabajo is not None and pid != os.getpid()
        ]
        for pid in sobrevivientes:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # ya terminó
        # Recolecta cualquier hijo directo que haya quedado como zombi.
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break  # ya no quedan hijos
            if pid == 0:
                break  # hay hijos, pero ninguno terminado
        if not sobrevivientes or time.time() >= limite:
            break
        time.sleep(0.05)

def liberar_recursos():
    """Al salir, por la razón que sea, termina y recolecta todos los trabajos activos."""
    global cola_cerrandose
    if os.name == "posix":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # que otra señal no corte la limpieza
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)       # ni un Ctrl+C
    cerrando.set()
    hilo_recolector.join(timeout=1)                    # que no compita con la limpieza
    with condicion_cola:
        cola_cerrandose = True  # la cola ya no inicia más trabajos
        condicion_cola.notify_all()

    def terminar_activos():
        for trabajo in todos_los_trabajos():
            id_trabajo = trabajo["id"]
            estado_trabajo(trabajo)
            with bloqueo_trabajos:
                proceso = trabajo["proceso"]
                if proceso is not None:
                    trabajo["interrumpido"] = True
            if proceso is not None and not trabajo.get("es_cola"):
                # Afuera (Avance 01): al salir se terminan como antes, sin escalamiento.
                terminar_trabajo_afuera(trabajo)
                finalizar_trabajo(id_trabajo, trabajo, proceso.returncode)
            elif proceso is not None:
                senal = terminar_proceso(proceso)
                if senal is not None:
                    trabajo["senal_final"] = senal
                    trabajo["motivo_fin"] = estados.MOTIVO_CIERRE
                finalizar_trabajo(id_trabajo, trabajo, proceso.returncode)

    terminar_activos()
    # El hilo de la cola pudo estar lanzando un trabajo justo ahora: se espera a
    # que termine y se revisa otra vez para que ningún proceso quede vivo.
    hilo_cola.join(timeout=3)
    for hilo in list(hilos_de_cola):
        hilo.join(timeout=3)   # los que estaban arrancando terminan su proceso por su cuenta
    terminar_activos()
    barrido_final()   # escapados de su grupo, zombis y grupos de Windows
    guardar_trabajos()


# atexit corre los registros en orden inverso: primero se liberan los recursos
# y al final se registra SYSTEM_STOPPED en la bitácora.
atexit.register(liberar_recursos)


def cerrar_por_senal(numero, _marco):
    """SIGTERM (kill) y SIGHUP (cerrar la terminal) cierran el programa de forma ordenada."""
    sys.exit(128 + numero)  # sys.exit hace que se ejecute liberar_recursos


if os.name == "posix":
    signal.signal(signal.SIGTERM, cerrar_por_senal)
    signal.signal(signal.SIGHUP, cerrar_por_senal)

while True:
    try:
        entrada = input("Q-umplidor> ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        break

    partes = entrada.split()

    if len(partes) == 0:
        continue

    # "queue cancelar <id>" cancela trabajos de la cola; "cancelar <id>" solo los
    # de fuera de ella. Sin esto, queue lo formaría como un comando de bash
    # llamado "cancelar" y no cancelaría nada.
    desde_cola = False
    if len(partes) >= 2 and partes[0] == "queue" and partes[1] == "cancelar":
        partes = partes[1:]
        desde_cola = True

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
        print("  cancelar <id>       Cancelar un trabajo en ejecución.")

        print("\n-------------------- AVANCE 02 --------------------\n")

        print("  queue <comando>     Ejecutar echo, sleep (&) o un programa en cola.")
        print("  queue               Mostrar la cola de trabajos.")
        print("  queue clear         Quitar de la cola los trabajos terminados y sus salidas.")
        print("  queue cancelar <id> Cancelar un trabajo de la cola.")
        print("  salida <id>         Mostrar la salida estándar (stdout) de un trabajo de la cola.")
        print("  errores <id>        Mostrar la salida de error (stderr) de un trabajo de la cola.")
        print("  limite              Ver el límite de concurrencia.")
        print("  limite <N>          Cambiar el límite de concurrencia.")
        print("  politica            Ver la política de escalamiento (SIGTERM -> SIGKILL).")
        print("  eventos [id]        Consultar la bitácora de eventos.")
        print("  recursos            Revisar procesos y archivos que siguen en uso.")
        print("  help                Mostrar esta ayuda.")

    elif partes[0] == "limite":
        concurrencia.atender_comando_limite(partes, control_concurrencia, avisar_despachador)

    elif partes[0] == "politica":
        if len(partes) != 1:
            print("politica: no acepta argumentos. Uso: politica")
            continue
        escalamiento.mostrar_politica(politica)

    elif partes[0] == "queue":
        if len(partes) == 1:
            mostrar_cola()
            continue
        # Sin esto, "queue clear" se encolaría como el comando de bash "clear".
        if len(partes) == 2 and partes[1] == "clear":
            limpiar_cola_terminados()
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
        try:
            shlex.split(comando_cola)
        except ValueError:
            print("queue: comillas sin cerrar")
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
                proceso = lanzar_trabajo(
                    siguiente_id, [sys.executable, "-c", f"import time; time.sleep({segundos})"]
                )
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
            registrar_trabajo(proceso, entrada)
        except OSError as error:
            BITACORA.record(ev.JOB_REJECTED, comando=argumentos[0], motivo=error.strerror)
            print(f"ejecutar: no se pudo iniciar '{argumentos[0]}': {error.strerror}")
            continue

    # Mostrar stdout o stderr de un trabajo
    elif partes[0] in ("salida", "errores"):
        id_trabajo = obtener_id(partes, partes[0], de_cola=True)
        if id_trabajo is not None:
            if partes[0] == "salida":
                mostrar_archivo(id_trabajo, 0, "salida", "la salida estándar")
            else:
                mostrar_archivo(id_trabajo, 1, "errores", "la salida de error")

    # Consulta el estado de un trabajo
    elif partes[0] == "estado":
        id_trabajo = obtener_id(partes, "estado", de_cola=False)
        if id_trabajo is not None:
            trabajo = trabajos[id_trabajo]
            estado = estado_trabajo(trabajo)
            print(f"[{id_trabajo}] {trabajo['comando']} -> {estado} ({tiempo_trabajo(trabajo)}s)")

    # Listar los trabajos
    elif partes[0] == "listar":
        if len(partes) != 1:
            print("listar: no acepta argumentos. Uso: listar")
            continue
        # La cola tiene su propio listado (queue); aquí solo van los de fuera.
        if not trabajos:
            print("No hay trabajos registrados")
        else:
            print(f"{'ID':<4} {'ESTADO':<20} {'TIEMPO':<8} COMANDO")
            for id_trabajo, trabajo in list(trabajos.items()):
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
        id_trabajo = obtener_id(partes, "cancelar", de_cola=desde_cola)
        if id_trabajo is not None and not desde_cola:
            # Afuera: la cancelación del Avance 01, sin bitácora ni escalamiento.
            trabajo = trabajos[id_trabajo]
            estado = estado_trabajo(trabajo)
            if trabajo["proceso"] is None:
                print(f"cancelar: el trabajo [{id_trabajo}] ya terminó ({estado})")
            else:
                trabajo["cancelado"] = True
                terminar_trabajo_afuera(trabajo)
                estado_trabajo(trabajo)
                print(f"Trabajo [{id_trabajo}] cancelado")
        elif id_trabajo is not None:
            trabajo = trabajos_cola[id_trabajo]
            estado_trabajo(trabajo)  # refresca si el proceso ya terminó
            a_terminar = None
            with bloqueo_trabajos:
                proceso = trabajo["proceso"]
                if trabajo["fin"] is not None:
                    # Ya terminó o ya estaba cancelado: repetir la petición no cambia nada
                    if trabajo["estado"] == "Cancelado":
                        print(f"cancelar: el trabajo [{id_trabajo}] ya estaba cancelado")
                    else:
                        print(f"cancelar: el trabajo [{id_trabajo}] ya terminó ({trabajo['estado']})")
                elif trabajo["cancelado"]:
                    print(f"cancelar: ya hay una cancelación en curso para el trabajo [{id_trabajo}]")
                elif proceso is None and trabajo["estado"] == "En cola":
                    # Nunca empezó: se cancela sin lanzar ningún proceso
                    trabajo["cancelado"] = True
                    trabajo["estado"] = "Cancelado"
                    trabajo["fin"] = time.time()
                    with condicion_cola:
                        try:
                            cola_ids.remove(id_trabajo)
                        except ValueError:
                            pass  # el hilo de la cola ya lo había sacado
                    guardar_trabajos()
                    for ruta in rutas_salida(id_trabajo, de_cola=True):
                        ruta.unlink(missing_ok=True)  # nunca corrió: no conserva archivos
                    BITACORA.record(ev.JOB_CANCEL_REQUESTED, id_trabajo)
                    BITACORA.record(ev.JOB_CANCELLED, id_trabajo, estado="Cancelado", antes="En cola")
                    print(f"Trabajo [{id_trabajo}] cancelado (estaba en cola)")
                else:
                    trabajo["cancelado"] = True
                    trabajo["motivo_fin"] = estados.MOTIVO_USUARIO
                    BITACORA.record(ev.JOB_CANCEL_REQUESTED, id_trabajo)
                    if proceso is None:
                        print(f"Trabajo [{id_trabajo}] se está iniciando; se cancelará en cuanto arranque")
                    else:
                        a_terminar = proceso
            if a_terminar is not None:
                # Política de escalamiento (RF-30): SIGTERM -> gracia -> SIGKILL.
                senal = terminar_proceso(a_terminar)
                if senal is not None:
                    trabajo["senal_final"] = senal
                estado_trabajo(trabajo)
                if senal == "SIGKILL":
                    print(f"Trabajo [{id_trabajo}] cancelado (no respondió a SIGTERM en "
                          f"{politica.gracia:g}s, se forzó con SIGKILL)")
                else:
                    print(f"Trabajo [{id_trabajo}] cancelado")

       # Consultar la bitácora de eventos
    elif partes[0] == "eventos":
        if len(partes) > 2:
            print("eventos: argumentos incorrectos. Uso: eventos [id]")
            continue
        filtro = None
        if len(partes) == 2:
            try:
                filtro = int(partes[1])
            except ValueError:
                print("eventos: el ID debe ser un número")
                continue
        registros = BITACORA.read(job_id=filtro, last=None if filtro else 20)
        if not registros:
            print("No hay eventos registrados")
        else:
            for registro in registros:
                print(ev.format_entry(registro))

    # Revisar procesos y archivos que siguen en uso
    elif partes[0] == "recursos":
        if len(partes) != 1:
            print("recursos: no acepta argumentos. Uso: recursos")
            continue
        mostrar_recursos()

    # Manejar comandos inválidos sin terminar el servicio
    else:
        print(f"{partes[0]}: comando no reconocido")

