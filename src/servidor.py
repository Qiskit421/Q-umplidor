"""Q-umplidor Network Edition: servidor.

Abre el Q-umplidor de siempre (la misma cola, persistencia y bitácora) y,
además, escucha la red para que otras computadoras usen la cola con cliente.py.

Por defecto solo escucha en localhost (RNF-12) y solo acepta las redes de
Q_REDES_PERMITIDAS (RF-20, RNF-13).

Uso: python servidor.py
"""
import io
import json
import os
import secrets
import socket
import sys
import threading
import time

import control_acceso
import event_log as ev
import main  # arranca Q-umplidor: carga la cola, el candado de una sola instancia, etc.
import protocolo
import atexit


def _leer_puerto():
    valor = os.environ.get("Q_PUERTO", "5000")
    try:
        puerto = int(valor)
        if not 1024 <= puerto <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit(f"Q_PUERTO debe ser un entero entre 1024 y 65535 (se recibió '{valor}')")
    return puerto


PUERTO = _leer_puerto()                                # conexión de los clientes (TCP), RF-16
INTERFAZ = os.environ.get("Q_INTERFAZ", "127.0.0.1")   # RNF-12: solo localhost por defecto
PUERTO_DESCUBRIMIENTO = 5001   # para que el cliente encuentre al servidor solo (UDP)
MENSAJE_BUSQUEDA = b"Q-UMPLIDOR?"
INTENTOS_CLAVE = 3
MAX_CLIENTES = 5               # RF-23, RNF-29
TIEMPO_AUTENTICACION = 30      # segundos para escribir la clave; quien no lo hace no ocupa un lugar

POLITICA = control_acceso.AccessPolicy(control_acceso.leer_redes_permitidas())
clientes_activos = threading.BoundedSemaphore(MAX_CLIENTES)

cierre_red = threading.Event()   # RF-15: el servidor de red se está cerrando
conexiones = set()               # conexiones abiertas, para cerrarlas al apagar
bloqueo_conexiones = threading.Lock()
socket_escucha = None

def leer_inactividad():
    """Segundos que una conexión puede estar callada antes de cerrarla (RF-22).
    Se configura con Q_INACTIVIDAD; por defecto 300 (5 minutos)."""
    valor = os.environ.get("Q_INACTIVIDAD", "300")
    try:
        segundos = int(valor)
        if segundos < 1:
            raise ValueError
    except ValueError:
        raise SystemExit(f"Q_INACTIVIDAD debe ser un entero mayor o igual a 1 (se recibió '{valor}')")
    return segundos


TIEMPO_INACTIVO = leer_inactividad()

# Eventos de red que se agregan a la bitácora (RF-22, RF-28).
CLIENT_CONNECTED = "CLIENT_CONNECTED"
CLIENT_DISCONNECTED = "CLIENT_DISCONNECTED"
RESPONSE_NOT_DELIVERED = "RESPONSE_NOT_DELIVERED"  # el comando se ejecutó, pero el cliente ya no estaba

CLAVE = f"{secrets.randbelow(10**6):06d}"  # nueva en cada arranque; se muestra en la pantalla del servidor


class SalidaPorHilo:
    """Reemplaza a sys.stdout: lo que imprime un comando remoto se le regresa a
    su cliente; todo lo demás sale en la pantalla del servidor como siempre."""

    def __init__(self, real):
        self._real = real
        self._local = threading.local()

    def capturar(self):
        self._local.buffer = io.StringIO()

    def soltar(self):
        texto = self._local.buffer.getvalue()
        self._local.buffer = None
        return texto

    def write(self, texto):
        buffer = getattr(self._local, "buffer", None)
        return (buffer if buffer is not None else self._real).write(texto)

    def flush(self):
        self._real.flush()

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def ip_local():
    """IP de esta computadora en la red local (la que deben usar los clientes)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prueba:
        try:
            prueba.connect(("10.255.255.255", 1))  # no envía nada; solo elige la interfaz de red
            return prueba.getsockname()[0]
        except OSError:
            return "127.0.0.1"


enviar = protocolo.enviar_mensaje


def despedir(conexion, motivo):
    """Avisa al cliente por qué se cierra la conexión, si todavía se puede."""
    try:
        enviar(conexion, {"error": motivo, "cerrar": True})
    except OSError:
        pass  # el cliente ya no está; no hay a quién avisar


def ejecutar_remoto(comando, origen):
    """Atiende un comando que llegó por la red (los mismos que en la terminal
    del servidor) y devuelve lo que imprimió."""
    partes = comando.split()
    if not partes:
        return ""
    sys.stdout.capturar()
    try:
        # RF-02, RNF-14: el rechazo se imprime dentro de la captura, así le llega al cliente.
        if not main.solicitud_valida(comando, origen=origen):
            return sys.stdout.soltar()
        if len(partes) == 2 and partes[0] == "sleep":
            main.atender(comando)  # sleep en primer plano: espera el cliente, no los demás
        else:
            with main.bloqueo_comandos:
                main.atender(comando)
    except Exception as error:  # un comando remoto no debe tumbar al servidor
        print(f"error: ocurrió un problema inesperado al ejecutar '{comando}' ({error})")
    return sys.stdout.soltar()


def rechazar(conexion, ip, motivo, mensaje):
    """Registra el rechazo, avisa al cliente con un mensaje útil y cierra (RF-02, RF-23, RNF-21)."""
    main.BITACORA.record(ev.ACCESS_DENIED, ip=ip, motivo=motivo)  # nunca la clave (RNF-15)
    try:
        enviar(conexion, {"ok": False, "mensaje": mensaje})
    except OSError:
        pass
    finally:
        conexion.close()


def atender_cliente(conexion, direccion):
    """Atiende a un cliente hasta que se va, se queda callado o manda algo inválido.

    Ninguna falla de un cliente debe tumbar al servidor ni dejar trabajos a
    medias: cada desconexión queda en la bitácora con su motivo (RF-22, RF-28).
    Al terminar, siempre libera su lugar en el límite de clientes (RF-23).
    """
    ip = direccion[0]
    cliente = f"{ip}:{direccion[1]}"
    autenticado = False
    motivo = "el cliente cerró la conexión"
    espera = TIEMPO_AUTENTICACION
    conexion.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # detecta conexiones muertas (cable, wifi)
    conexion.settimeout(espera)
    lector = protocolo.LectorMensajes(conexion)
    try:
        for _ in range(INTENTOS_CLAVE):
            try:
                clave = lector.leer().get("clave")
            except protocolo.MensajeInvalido:
                clave = None
            if clave == CLAVE:
                enviar(conexion, {"ok": True, "servidor": socket.gethostname()})
                autenticado = True
                break
            time.sleep(1)  # frena a quien intente adivinar la clave
            enviar(conexion, {"ok": False, "mensaje": "clave incorrecta"})
        if not autenticado:
            motivo = "demasiados intentos de clave"
            main.BITACORA.record(ev.ACCESS_DENIED, ip=ip, motivo="CLAVE_INCORRECTA")  # nunca la clave (RNF-15)
            return
        espera = TIEMPO_INACTIVO
        conexion.settimeout(espera)
        main.BITACORA.record(CLIENT_CONNECTED, cliente=cliente)

        while True:
            try:
                mensaje = lector.leer()
            except protocolo.MensajeInvalido as error:
                enviar(conexion, {"salida": f"error: petición no válida ({error})\n"})
                continue
            if "comando" not in mensaje:
                enviar(conexion, {"salida": "error: petición no válida (falta el campo comando)\n"})
                continue
            comando = str(mensaje["comando"]).strip()
            salida = ejecutar_remoto(comando, ip)
            try:
                enviar(conexion, {"salida": salida})
            except OSError:
                # El comando sí se ejecutó; lo que se perdió fue la respuesta (RF-28).
                main.BITACORA.record(RESPONSE_NOT_DELIVERED, cliente=cliente, comando=comando)
                raise
    except protocolo.ConexionCerrada as cerrada:
        if cerrada.incompletos:
            motivo = f"el cliente cerró la conexión a mitad de un mensaje ({cerrada.incompletos} bytes descartados)"
    except socket.timeout:  # en Python 3.10+ es lo mismo que TimeoutError
        if autenticado:
            motivo = f"inactividad ({espera} s sin mensajes)"
            despedir(conexion, f"desconectado por inactividad ({espera} s sin mensajes)")
        else:
            motivo = f"no se autenticó en {espera} s"
            main.BITACORA.record(ev.ACCESS_DENIED, ip=ip, motivo="SIN_AUTENTICAR")
    except protocolo.MensajeDemasiadoGrande as error:
        motivo = f"mensaje demasiado grande: {error}"
        despedir(conexion, f"mensaje demasiado grande (máximo {protocolo.MAX_MENSAJE} bytes)")
    except OSError as error:
        motivo = f"conexión perdida ({error.strerror or error})"
    except Exception as error:  # nada de un cliente debe tumbar al servidor
        motivo = f"error inesperado ({type(error).__name__}: {error})"
    finally:
        try:
            conexion.close()
        finally:
            with bloqueo_conexiones:
                conexiones.discard(conexion)
            clientes_activos.release()  # se libera el lugar tomado en escuchar_clientes
        if cierre_red.is_set():
            motivo = "el servicio se cerró"
        if autenticado:
            main.BITACORA.record(CLIENT_DISCONNECTED, cliente=cliente, motivo=motivo)

def escuchar_clientes(servidor):
    while not cierre_red.is_set():
        try:
            conexion, direccion = servidor.accept()
        except OSError:
            break  # el socket de escucha se cerró: el servicio se está apagando
        if cierre_red.is_set():
            conexion.close()
            break
        ip = direccion[0]
        if not POLITICA.is_allowed(ip):  # RF-20: antes de leer nada
            rechazar(conexion, ip, "IP_NO_PERMITIDA",
                     "acceso denegado: su dirección no está autorizada. Pida al administrador agregar su red.")
            continue
        if not clientes_activos.acquire(blocking=False):  # RF-23
            rechazar(conexion, ip, "MAX_CLIENTES",
                     "servidor ocupado: demasiados clientes conectados. Intente más tarde.")
            continue
        with bloqueo_conexiones:
            conexiones.add(conexion)
        threading.Thread(target=atender_cliente, args=(conexion, direccion), daemon=True).start()


def responder_busquedas():
    """Contesta a los clientes que buscan un servidor en la red (python cliente.py sin IP)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.bind(("", PUERTO_DESCUBRIMIENTO))
        except OSError:
            return  # sin búsqueda automática: los clientes pueden usar la IP
        udp.settimeout(0.5)  # para revisar si el servidor se está cerrando
        while not cierre_red.is_set():
            try:
                datos, direccion = udp.recvfrom(1024)
            except OSError:
                continue  # incluye el tiempo de espera agotado y el error de Windows de siempre
            if datos == MENSAJE_BUSQUEDA and POLITICA.is_allowed(direccion[0]):
                respuesta = {"puerto": PUERTO, "nombre": socket.gethostname()}
                udp.sendto(json.dumps(respuesta).encode("utf-8"), direccion)

def cerrar_red():
    """Cierre ordenado de la red (RF-15, RNF-25). Corre al salir, antes de liberar la cola."""
    print("\nCerrando Q-umplidor: ya no se aceptan trabajos nuevos...")
    try:
        main.empezar_cierre()   # 1. desde aquí se rechazan trabajos nuevos
    except Exception as error:  # que un fallo aquí no impida cerrar la red
        print(f"[aviso] no se pudo registrar el inicio del cierre: {error}")
    cierre_red.set()
    if socket_escucha is not None:
        try:
            socket_escucha.shutdown(socket.SHUT_RDWR)  # despierta a accept() en Linux
        except OSError:
            pass  # en Windows un socket de escucha no admite shutdown; close() basta
        socket_escucha.close()                         # 2. el puerto queda libre
    with bloqueo_conexiones:
        abiertas = list(conexiones)
    for conexion in abiertas:
        despedir(conexion, "el servicio se está cerrando")
        try:
            conexion.shutdown(socket.SHUT_RDWR)        # despierta al hilo que espera mensajes
        except OSError:
            pass
    limite = time.time() + 3
    while time.time() < limite:                        # espera a que cada hilo se despida
        with bloqueo_conexiones:
            if not conexiones:
                break
        time.sleep(0.05)
    print(f"Red cerrada ({len(abiertas)} clientes desconectados). Deteniendo trabajos...")

def iniciar():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Tras cerrar el servidor con clientes conectados, el puerto queda en TIME_WAIT
    # cerca de un minuto; sin esto, reiniciarlo falla con "Address already in use".
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        servidor.bind((INTERFAZ, PUERTO))
        servidor.listen()
    except OSError as error:
        raise SystemExit(f"No se pudo abrir {INTERFAZ}:{PUERTO} para la red: {error.strerror}")
    main.INFO_RED = f"escuchando en {INTERFAZ}:{PUERTO} (máximo {MAX_CLIENTES} clientes)"
    global socket_escucha
    socket_escucha = servidor
    atexit.register(cerrar_red)  # se registra después de importar main: corre ANTES que liberar_recursos
    sys.stdout = SalidaPorHilo(sys.stdout)
    threading.Thread(target=escuchar_clientes, args=(servidor,), daemon=True).start()
    threading.Thread(target=responder_busquedas, daemon=True).start()

    ip = ip_local() if INTERFAZ == "0.0.0.0" else INTERFAZ
    print("Q-umplidor Network Edition - servidor")
    print(f"  Dirección:       {ip}:{PUERTO}")
    print(f"  Clave de acceso: {CLAVE}")
    if INTERFAZ == "0.0.0.0":
        print("  [aviso] escuchando en todas las interfaces; solo se aceptan las redes de Q_REDES_PERMITIDAS")
    print(f"  Inactividad:     se desconecta a un cliente tras {TIEMPO_INACTIVO} s sin mensajes")
    print("  En la otra computadora: python cliente.py")
    print(f"  (si no encuentra el servidor: python cliente.py {ip})")
    print()
    main.repl()


if __name__ == "__main__":
    iniciar()