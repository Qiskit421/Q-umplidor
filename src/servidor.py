"""Q-umplidor Network Edition: servidor.

Abre el Q-umplidor de siempre (la misma cola, persistencia y bitácora) y,
además, escucha la red para que otras computadoras usen la cola con cliente.py.

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

import main  # arranca Q-umplidor: carga la cola, el candado de una sola instancia, etc.
import protocolo

PUERTO = 5000                  # conexión de los clientes (TCP)
PUERTO_DESCUBRIMIENTO = 5001   # para que el cliente encuentre al servidor solo (UDP)
MENSAJE_BUSQUEDA = b"Q-UMPLIDOR?"
INTENTOS_CLAVE = 3


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


def ejecutar_remoto(comando):
    """Atiende un comando que llegó por la red (los mismos que en la terminal
    del servidor) y devuelve lo que imprimió."""
    partes = comando.split()
    if not partes:
        return ""
    sys.stdout.capturar()
    try:
        if len(partes) == 2 and partes[0] == "sleep":
            main.atender(comando)  # sleep en primer plano: espera el cliente, no los demás
        else:
            with main.bloqueo_comandos:
                main.atender(comando)
    except Exception as error:  # un comando remoto no debe tumbar al servidor
        print(f"error: ocurrió un problema inesperado al ejecutar '{comando}' ({error})")
    return sys.stdout.soltar()


def atender_cliente(conexion, direccion):
    """Atiende a un cliente hasta que se va, se queda callado o manda algo inválido.

    Ninguna falla de un cliente debe tumbar al servidor ni dejar trabajos a
    medias: cada desconexión queda en la bitácora con su motivo (RF-22, RF-28).
    """
    cliente = f"{direccion[0]}:{direccion[1]}"
    autenticado = False
    motivo = "el cliente cerró la conexión"
    conexion.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # detecta conexiones muertas (cable, wifi)
    conexion.settimeout(TIEMPO_INACTIVO)
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
            return
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
            salida = ejecutar_remoto(comando)
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
        motivo = f"inactividad ({TIEMPO_INACTIVO} s sin mensajes)"
        despedir(conexion, f"desconectado por inactividad ({TIEMPO_INACTIVO} s sin mensajes)")
    except protocolo.MensajeDemasiadoGrande as error:
        motivo = f"mensaje demasiado grande: {error}"
        despedir(conexion, f"mensaje demasiado grande (máximo {protocolo.MAX_MENSAJE} bytes)")
    except OSError as error:
        motivo = f"conexión perdida ({error.strerror or error})"
    except Exception as error:  # nada de un cliente debe tumbar al servidor
        motivo = f"error inesperado ({type(error).__name__}: {error})"
    finally:
        conexion.close()
        if autenticado:
            main.BITACORA.record(CLIENT_DISCONNECTED, cliente=cliente, motivo=motivo)


def escuchar_clientes(servidor):
    while True:
        conexion, direccion = servidor.accept()
        threading.Thread(target=atender_cliente, args=(conexion, direccion), daemon=True).start()


def responder_busquedas():
    """Contesta a los clientes que buscan un servidor en la red (python cliente.py sin IP)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        try:
            udp.bind(("", PUERTO_DESCUBRIMIENTO))
        except OSError:
            return  # sin búsqueda automática: los clientes pueden usar la IP
        while True:
            try:
                datos, direccion = udp.recvfrom(1024)
            except OSError:
                continue  # en Windows, una respuesta que no llegó aparece aquí como error
            if datos == MENSAJE_BUSQUEDA:
                respuesta = {"puerto": PUERTO, "nombre": socket.gethostname()}
                udp.sendto(json.dumps(respuesta).encode("utf-8"), direccion)


def iniciar():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Tras cerrar el servidor con clientes conectados, el puerto queda en TIME_WAIT
    # cerca de un minuto; sin esto, reiniciarlo falla con "Address already in use".
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        servidor.bind(("0.0.0.0", PUERTO))
        servidor.listen()
    except OSError as error:
        raise SystemExit(f"No se pudo abrir el puerto {PUERTO} para la red: {error.strerror}")

    sys.stdout = SalidaPorHilo(sys.stdout)
    threading.Thread(target=escuchar_clientes, args=(servidor,), daemon=True).start()
    threading.Thread(target=responder_busquedas, daemon=True).start()

    ip = ip_local()
    print("Q-umplidor Network Edition - servidor")
    print(f"  Dirección:       {ip}:{PUERTO}")
    print(f"  Clave de acceso: {CLAVE}")
    print(f"  Inactividad:     se desconecta a un cliente tras {TIEMPO_INACTIVO} s sin mensajes")
    print("  En la otra computadora: python cliente.py")
    print(f"  (si no encuentra el servidor: python cliente.py {ip})")
    print()
    main.repl()


if __name__ == "__main__":
    iniciar()
