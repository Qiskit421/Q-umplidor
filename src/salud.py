"""Resumen de salud del servicio (RF-24).

Solo arma el texto a partir de los datos que recibe: no toca la cola, los
procesos ni la bitácora, para poder probarlo sin arrancar main.py.
"""
from datetime import datetime

import event_log as ev

MAX_ERRORES = 5


def es_error(registro):
    """True si el evento de la bitácora cuenta como error reciente."""
    evento = registro.get("event")
    if evento in (ev.JOB_REJECTED, ev.ACCESS_DENIED, ev.JOB_INTERRUPTED):
        return True
    if evento == ev.JOB_FINISHED:
        return str(registro.get("details", {}).get("estado", "")).startswith("Falló")
    return False


def errores_recientes(registros, cantidad=MAX_ERRORES):
    """Devuelve (los últimos errores, cuántos errores hay en total)."""
    errores = [r for r in registros if es_error(r)]
    return errores[-cantidad:], len(errores)


def formatear_duracion(segundos):
    segundos = max(0, int(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas}h {minutos:02d}m {segundos:02d}s"


def construir_resumen(inicio, ahora, en_ejecucion, limite, en_cola, capacidad,
                      en_segundo_plano, registros, red=None, directorio_datos=None):
    """Devuelve las líneas del resumen de salud."""
    desde = datetime.fromtimestamp(inicio).strftime("%Y-%m-%d %H:%M:%S")
    lineas = [f"Servicio ................... ACTIVO desde {desde} ({formatear_duracion(ahora - inicio)})"]
    if red:
        lineas.append(f"Servidor de red ............. {red}")
    if directorio_datos:
        lineas.append(f"Directorio de datos ......... {directorio_datos}")
    lineas.append(f"Trabajos en ejecución ....... {en_ejecucion} de {limite} (límite de concurrencia)")
    lineas.append(f"Trabajos en cola ............ {en_cola} de {capacidad} (capacidad de la cola)")
    lineas.append(f"Trabajos en segundo plano ... {en_segundo_plano} (fuera de la cola)")
    recientes, total = errores_recientes(registros)
    if not recientes:
        lineas.append("Errores recientes ........... ninguno")
    else:
        lineas.append(f"Errores recientes ........... últimos {len(recientes)} de {total} en la bitácora")
        lineas += [f"  {ev.format_entry(r)}" for r in recientes]
    return lineas