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
LIMITE_LINEA = 2048            # RNF-14: tamaño máximo de un mensaje de red

POLITICA = control_acceso.AccessPolicy(control_acceso.leer_redes_permitidas())
clientes_activos = threading.BoundedSemaphore(MAX_CLIENTES)

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


def enviar(conexion, datos):
    conexion.sendall((json.dumps(datos, ensure_ascii=False) + "\n").encode("utf-8"))


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


def atender_cliente(conexion, ip):
    conectado = False
    try:
        conexion.settimeout(30)  # quien no se autentica a tiempo no ocupa un lugar
        with conexion, conexion.makefile("r", encoding="utf-8") as lector:
            for _ in range(INTENTOS_CLAVE):
                linea = lector.readline(LIMITE_LINEA + 1)
                if not linea or len(linea) > LIMITE_LINEA:
                    return
                try:
                    clave = json.loads(linea).get("clave")
                except (ValueError, AttributeError):
                    clave = None
                if clave == CLAVE:
                    enviar(conexion, {"ok": True, "servidor": socket.gethostname()})
                    conectado = True
                    break
                time.sleep(1)  # frena a quien intente adivinar la clave
                enviar(conexion, {"ok": False, "mensaje": "clave incorrecta"})
            if not conectado:
                main.BITACORA.record(ev.ACCESS_DENIED, ip=ip, motivo="CLAVE_INCORRECTA")
                return
            conexion.settimeout(None)

            while True:
                linea = lector.readline(LIMITE_LINEA + 1)
                if not linea:
                    break
                if len(linea) > LIMITE_LINEA:
                    main.BITACORA.record(ev.JOB_REJECTED, comando=linea[:80],
                                         motivo="mensaje de red demasiado largo", origen=ip)
                    enviar(conexion, {"salida": f"rechazado: mensaje demasiado largo (máximo {LIMITE_LINEA}).\n"})
                    return
                try:
                    comando = str(json.loads(linea)["comando"]).strip()
                except (ValueError, KeyError, TypeError):
                    enviar(conexion, {"salida": "error: petición no válida\n"})
                    continue
                enviar(conexion, {"salida": ejecutar_remoto(comando, ip)})
    except OSError:
        pass  # el cliente se fue sin avisar
    finally:
        clientes_activos.release()


def escuchar_clientes(servidor):
    while True:
        conexion, direccion = servidor.accept()
        ip = direccion[0]
        if not POLITICA.is_allowed(ip):  # RF-20: antes de leer nada
            rechazar(conexion, ip, "IP_NO_PERMITIDA",
                     "acceso denegado: su dirección no está autorizada. Pida al administrador agregar su red.")
            continue
        if not clientes_activos.acquire(blocking=False):  # RF-23
            rechazar(conexion, ip, "MAX_CLIENTES",
                     "servidor ocupado: demasiados clientes conectados. Intente más tarde.")
            continue
        threading.Thread(target=atender_cliente, args=(conexion, ip), daemon=True).start()


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
            if datos == MENSAJE_BUSQUEDA and POLITICA.is_allowed(direccion[0]):
                respuesta = {"puerto": PUERTO, "nombre": socket.gethostname()}
                udp.sendto(json.dumps(respuesta).encode("utf-8"), direccion)


def iniciar():
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        servidor.bind((INTERFAZ, PUERTO))
        servidor.listen()
    except OSError as error:
        raise SystemExit(f"No se pudo abrir {INTERFAZ}:{PUERTO} para la red: {error.strerror}")
    main.INFO_RED = f"escuchando en {INTERFAZ}:{PUERTO} (máximo {MAX_CLIENTES} clientes)"
    sys.stdout = SalidaPorHilo(sys.stdout)
    threading.Thread(target=escuchar_clientes, args=(servidor,), daemon=True).start()
    threading.Thread(target=responder_busquedas, daemon=True).start()

    ip = ip_local() if INTERFAZ == "0.0.0.0" else INTERFAZ
    print("Q-umplidor Network Edition - servidor")
    print(f"  Dirección:       {ip}:{PUERTO}")
    print(f"  Clave de acceso: {CLAVE}")
    if INTERFAZ == "0.0.0.0":
        print("  [aviso] escuchando en todas las interfaces; solo se aceptan las redes de Q_REDES_PERMITIDAS")
    print("  En la otra computadora: python cliente.py")
    print(f"  (si no encuentra el servidor: python cliente.py {ip})")
    print()
    main.repl()


if __name__ == "__main__":
    iniciar()