"""Estados y tiempos de un trabajo (RF-06).

El código guarda los estados en español ("En cola", "Terminado", ...) para no
romper el historial ya guardado en data/trabajos.json. Este módulo los traduce
a los nombres que pide el cliente y calcula los tiempos de cada trabajo:

  Estado interno              Estado del cliente
  --------------------------  ------------------
  En cola                     QUEUED
  En ejecución                RUNNING
  Terminado                   SUCCEEDED
  Falló (...)                 FAILED
  Cancelado                   CANCELED
  Interrumpido                INTERRUPTED  (extra: el servicio se cerró)

Tiempos que se registran por trabajo:
  - envío:  cuando el usuario lo mandó (momento_encolado, o inicio si arrancó directo)
  - inicio: cuando arrancó su proceso
  - fin:    cuando terminó, falló, se canceló o se interrumpió
  - espera     = inicio - envío   (tiempo en QUEUED)
  - ejecución  = fin - inicio     (tiempo en RUNNING)
"""

import time
from datetime import datetime

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELED = "CANCELED"
INTERRUPTED = "INTERRUPTED"

ESTADOS_FINALES = {SUCCEEDED, FAILED, CANCELED, INTERRUPTED}

# Motivo que deja la política de escalamiento cuando un trabajo supera el
# tiempo máximo. Se termina como FAILED, no como CANCELED, porque nadie pidió
# cancelarlo: el trabajo no cumplió con el tiempo permitido.
MOTIVO_TIEMPO_MAXIMO = "tiempo máximo excedido"
MOTIVO_USUARIO = "cancelado por el usuario"
MOTIVO_CIERRE = "cierre de Q-umplidor"


def estado_cliente(estado_interno):
    """Traduce el estado guardado en el código al nombre del cliente."""
    if estado_interno == "En cola":
        return QUEUED
    if estado_interno == "En ejecución":
        return RUNNING
    if estado_interno == "Terminado":
        return SUCCEEDED
    if estado_interno.startswith("Falló"):
        return FAILED
    if estado_interno.startswith("Cancelado"):
        return CANCELED
    if estado_interno == "Interrumpido":
        return INTERRUPTED
    return estado_interno


def estado_final(trabajo, codigo):
    """Decide el estado interno cuando el proceso de un trabajo termina.

    Una sola regla para todos los caminos (trabajo directo, trabajo de la cola
    y escalamiento), para que nunca se contradigan.
    """
    if trabajo.get("motivo_fin") == MOTIVO_TIEMPO_MAXIMO:
        return f"Falló ({MOTIVO_TIEMPO_MAXIMO})"
    if trabajo.get("cancelado"):
        return "Cancelado"
    if codigo == 0:
        return "Terminado"
    return f"Falló (código {codigo})"


# ---------------------------------------------------------------- tiempos

def momento_envio(trabajo):
    """Hora en que se envió el trabajo."""
    return trabajo.get("momento_encolado") or trabajo.get("inicio")


def tiempo_espera(trabajo, ahora=None):
    """Segundos que el trabajo pasó (o lleva) en QUEUED."""
    envio = momento_envio(trabajo)
    if envio is None:
        return None
    ahora = time.time() if ahora is None else ahora
    hasta = trabajo.get("inicio") or trabajo.get("fin") or ahora
    return max(0.0, hasta - envio)


def tiempo_ejecucion(trabajo, ahora=None):
    """Segundos que el trabajo pasó (o lleva) en RUNNING. None si nunca arrancó."""
    inicio = trabajo.get("inicio")
    if inicio is None:
        return None
    ahora = time.time() if ahora is None else ahora
    return max(0.0, (trabajo.get("fin") or ahora) - inicio)


def formatear_hora(marca, con_fecha=False):
    if marca is None:
        return "-"
    formato = "%Y-%m-%d %H:%M:%S" if con_fecha else "%H:%M:%S"
    return datetime.fromtimestamp(marca).strftime(formato)


def formatear_duracion(segundos):
    if segundos is None:
        return "-"
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    if horas:
        return f"{horas}h{minutos:02d}m{segundos:02d}s"
    if minutos:
        return f"{minutos}m{segundos:02d}s"
    return f"{segundos}s"


# ---------------------------------------------------------- presentación

def detalle_estado(id_trabajo, trabajo, estado_interno):
    """Líneas que muestra el comando 'estado <id>'."""
    estado = estado_cliente(estado_interno)
    lineas = [
        f"[{id_trabajo}] {trabajo['comando']} -> {estado} ({estado_interno})",
        f"  Enviado:   {formatear_hora(momento_envio(trabajo), con_fecha=True)}",
        f"  Inicio:    {formatear_hora(trabajo.get('inicio'), con_fecha=True)}",
        f"  Fin:       {formatear_hora(trabajo.get('fin'), con_fecha=True)}",
        f"  Espera:    {formatear_duracion(tiempo_espera(trabajo))}",
        f"  Ejecución: {formatear_duracion(tiempo_ejecucion(trabajo))}",
    ]
    if trabajo.get("senal_final"):
        motivo = trabajo.get("motivo_fin") or MOTIVO_USUARIO
        if trabajo["senal_final"] == "SIGKILL":
            accion = "no respondió a SIGTERM, se forzó con SIGKILL"
        else:
            accion = "terminó con SIGTERM"
        lineas.append(f"  Escalamiento: {motivo}; {accion}")
    return lineas


ENCABEZADO_LISTAR = (
    f"{'ID':<4} {'ESTADO':<11} {'ENVIADO':<9} {'INICIO':<9} {'FIN':<9} "
    f"{'ESPERA':<8} {'EJECUCIÓN':<10} COMANDO"
)


def fila_listar(id_trabajo, trabajo, estado_interno):
    """Una fila del comando 'listar'."""
    return (
        f"{id_trabajo:<4} {estado_cliente(estado_interno):<11} "
        f"{formatear_hora(momento_envio(trabajo)):<9} "
        f"{formatear_hora(trabajo.get('inicio')):<9} "
        f"{formatear_hora(trabajo.get('fin')):<9} "
        f"{formatear_duracion(tiempo_espera(trabajo)):<8} "
        f"{formatear_duracion(tiempo_ejecucion(trabajo)):<10} "
        f"{trabajo['comando']}"
    )
