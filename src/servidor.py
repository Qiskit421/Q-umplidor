"""Q-umplidor Network Edition: servidor.

Abre el Q-umplidor de siempre (la misma cola, persistencia y bitácora) y,
además, escucha la red para que otras computadoras usen la cola con cliente.py.

Uso: python servidor.py
"""
import io
import json
import secrets
import socket
import sys
import threading
import time

import main  # arranca Q-umplidor: carga la cola, el candado de una sola instancia, etc.

PUERTO = 5000                  # conexión de los clientes (TCP)
PUERTO_DESCUBRIMIENTO = 5001   # para que el cliente encuentre al servidor solo (UDP)
MENSAJE_BUSQUEDA = b"Q-UMPLIDOR?"
INTENTOS_CLAVE = 3

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


def atender_cliente(conexion):
    conectado = False
    try:
        with conexion, conexion.makefile("r", encoding="utf-8") as lector:
            for _ in range(INTENTOS_CLAVE):
                linea = lector.readline()
                if not linea:
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
                return

            for linea in lector:
                try:
                    comando = str(json.loads(linea)["comando"]).strip()
                except (ValueError, KeyError, TypeError):
                    enviar(conexion, {"salida": "error: petición no válida\n"})
                    continue
                enviar(conexion, {"salida": ejecutar_remoto(comando)})
    except OSError:
        pass  # el cliente se fue sin avisar


def escuchar_clientes(servidor):
    while True:
        conexion, _ = servidor.accept()
        threading.Thread(target=atender_cliente, args=(conexion,), daemon=True).start()


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
    print("  En la otra computadora: python cliente.py")
    print(f"  (si no encuentra el servidor: python cliente.py {ip})")
    print()
    main.repl()


if __name__ == "__main__":
    iniciar()
