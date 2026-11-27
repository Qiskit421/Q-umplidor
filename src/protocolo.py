"""Protocolo de red de Q-umplidor: cómo se parten y se juntan los mensajes.

Formato (igual en los dos sentidos): cada mensaje es un objeto JSON en UTF-8
terminado en un salto de línea ("\\n"). Ejemplos:
    cliente -> servidor   {"clave": "123456"}
    cliente -> servidor   {"comando": "queue sleep 5"}
    servidor -> cliente   {"salida": "ID: [1] agregado a la cola\\n"}
    servidor -> cliente   {"error": "...", "cerrar": true}   (el servidor va a cerrar)

TCP entrega un flujo de bytes, no mensajes: un mensaje puede llegar partido en
varios recv() o pegado con el siguiente. LectorMensajes junta los pedazos hasta
encontrar el "\\n" y guarda lo que sobre para el siguiente mensaje (RF-21).
"""
import json

FIN = b"\n"
MAX_MENSAJE = 64 * 1024  # 64 KiB: más que suficiente para un comando; evita llenar la memoria


class MensajeInvalido(Exception):
    """El mensaje llegó completo pero no es UTF-8, no es JSON o no es un objeto.
    Se responde con un error y la conexión sigue."""


class MensajeDemasiadoGrande(Exception):
    """Llegaron más de MAX_MENSAJE bytes sin fin de mensaje. La conexión se cierra."""


class ConexionCerrada(Exception):
    """El otro lado cerró la conexión. 'incompletos' son los bytes de un mensaje
    que quedó a medias; se descartan porque nunca llegó completo."""

    def __init__(self, incompletos=0):
        super().__init__(f"conexión cerrada ({incompletos} bytes de un mensaje incompleto descartados)")
        self.incompletos = incompletos


def enviar_mensaje(conexion, datos):
    """Envía un mensaje completo. sendall repite el envío hasta mandar todos los
    bytes, aunque el sistema operativo solo acepte una parte en cada llamada."""
    conexion.sendall(json.dumps(datos, ensure_ascii=False).encode("utf-8") + FIN)


def decodificar(linea):
    """Convierte los bytes de un mensaje completo (sin el "\\n") en un dict."""
    linea = linea.rstrip(b"\r")  # por si el otro lado manda "\r\n"
    try:
        texto = linea.decode("utf-8")
    except UnicodeDecodeError:
        raise MensajeInvalido("el mensaje no está en UTF-8") from None
    try:
        datos = json.loads(texto)
    except ValueError:
        raise MensajeInvalido("el mensaje no es JSON válido") from None
    if not isinstance(datos, dict):
        raise MensajeInvalido("el mensaje debe ser un objeto JSON")
    return datos


class LectorMensajes:
    """Lee mensajes completos de un socket, sin importar cómo lleguen partidos."""

    def __init__(self, conexion, max_mensaje=MAX_MENSAJE):
        self.conexion = conexion
        self.max_mensaje = max_mensaje
        self.pendiente = bytearray()  # bytes recibidos que todavía no forman un mensaje completo

    def leer(self):
        """Devuelve el siguiente mensaje como dict.

        Lanza ConexionCerrada, MensajeDemasiadoGrande o MensajeInvalido; si el
        socket tiene timeout, también socket.timeout (TimeoutError).
        """
        while True:
            fin = self.pendiente.find(FIN)
            if fin != -1:
                linea = bytes(self.pendiente[:fin])
                del self.pendiente[:fin + 1]  # lo que sobra es el inicio del siguiente mensaje
                if len(linea) > self.max_mensaje:
                    raise MensajeDemasiadoGrande(f"mensaje de {len(linea)} bytes (máximo {self.max_mensaje})")
                return decodificar(linea)
            if len(self.pendiente) > self.max_mensaje:
                raise MensajeDemasiadoGrande(f"más de {self.max_mensaje} bytes sin fin de mensaje")
            trozo = self.conexion.recv(4096)
            if not trozo:
                incompletos = len(self.pendiente)
                self.pendiente.clear()
                raise ConexionCerrada(incompletos)
            self.pendiente += trozo
