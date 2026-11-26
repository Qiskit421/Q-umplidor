"""Q-umplidor Network Edition: cliente.

Usa la cola de un servidor Q-umplidor desde otra computadora de la misma red.
Los trabajos se ejecutan y se guardan en el servidor; aquí no se guarda nada.

Uso: python cliente.py            (busca el servidor solo)
     python cliente.py <IP>       (si la búsqueda no lo encuentra)
"""
import json
import socket
import sys

import protocolo

PUERTO = 5000
PUERTO_DESCUBRIMIENTO = 5001
MENSAJE_BUSQUEDA = b"Q-UMPLIDOR?"


def ip_local():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as prueba:
        try:
            prueba.connect(("10.255.255.255", 1))  # no envía nada; solo elige la interfaz de red
            return prueba.getsockname()[0]
        except OSError:
            return None


def buscar_servidor():
    """Pregunta a toda la red si hay un servidor Q-umplidor. Devuelve (ip, puerto, nombre) o None."""
    destinos = ["255.255.255.255", "127.0.0.1"]
    propia = ip_local()
    if propia:
        destinos.append(propia.rsplit(".", 1)[0] + ".255")  # la red local de esta computadora
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp.settimeout(2)
        for destino in destinos:
            try:
                udp.sendto(MENSAJE_BUSQUEDA, (destino, PUERTO_DESCUBRIMIENTO))
            except OSError:
                pass  # esa ruta no existe en esta red
        try:
            datos, (ip, _) = udp.recvfrom(1024)
            respuesta = json.loads(datos)
            return ip, int(respuesta["puerto"]), respuesta.get("nombre", ip)
        except (OSError, ValueError, KeyError):
            return None


enviar = protocolo.enviar_mensaje


class ServidorCerro(Exception):
    """El servidor avisó que cierra la conexión (por ejemplo, por inactividad)."""


def recibir(lector):
    """Lee la siguiente respuesta completa, aunque llegue en varios pedazos."""
    respuesta = lector.leer()
    if respuesta.get("cerrar"):
        raise ServidorCerro(respuesta.get("error", "el servidor cerró la conexión"))
    return respuesta


def main():
    if len(sys.argv) > 2:
        print("Uso: python cliente.py [IP del servidor]")
        return 1
    if len(sys.argv) == 2:
        ip, puerto, nombre = sys.argv[1], PUERTO, sys.argv[1]
    else:
        print("Buscando un servidor Q-umplidor en la red...")
        encontrado = buscar_servidor()
        if encontrado is None:
            print("No se encontró ningún servidor. Usa la IP que muestra el servidor:")
            print("  python cliente.py <IP del servidor>")
            return 1
        ip, puerto, nombre = encontrado

    try:
        conexion = socket.create_connection((ip, puerto), timeout=5)
    except OSError as error:
        print(f"No se pudo conectar con {ip}:{puerto}: {error.strerror or error}")
        return 1
    conexion.settimeout(None)

    lector = protocolo.LectorMensajes(conexion)
    with conexion:
        try:
            for intento in range(3):  # el servidor cierra la conexión al tercer intento fallido
                clave = input(f"Clave de acceso de {nombre}: ").strip()
                enviar(conexion, {"clave": clave})
                respuesta = recibir(lector)
                if respuesta.get("ok"):
                    nombre = respuesta.get("servidor", nombre)
                    break
                print("Clave incorrecta.")
            else:
                print("Demasiados intentos. Vuelve a ejecutar python cliente.py.")
                return 1

            print(f"Conectado a Q-umplidor en {nombre} ({ip}).")
            print("Escribe help para ver los comandos o salir para desconectarte.")
            while True:
                entrada = input(f"Q-umplidor@{ip}> ").strip()
                if not entrada:
                    continue
                if entrada in ("salir", "exit"):
                    break
                enviar(conexion, {"comando": entrada})
                print(recibir(lector).get("salida", ""), end="")
        except (KeyboardInterrupt, EOFError):
            print()
        except ServidorCerro as aviso:
            print(f"El servidor cerró la conexión: {aviso}")
            print("Vuelve a ejecutar python cliente.py para reconectarte.")
            return 1
        except (protocolo.ConexionCerrada, protocolo.MensajeInvalido, protocolo.MensajeDemasiadoGrande, OSError):
            print("Se perdió la conexión con el servidor.")
            print("Vuelve a ejecutar python cliente.py para reconectarte.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
