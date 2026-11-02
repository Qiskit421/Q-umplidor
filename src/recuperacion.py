"""Recuperación de trabajos huérfanos tras una caída de Q-umplidor (RF-13, ADR-0006).

Problema: si a Q-umplidor lo matan con SIGKILL (kill -9) o se cae, no alcanza a
detener sus trabajos. Como cada trabajo vive en su propio grupo de procesos
(start_new_session, ADR-0007), sigue corriendo sin dueño (su padre pasa a ser
el PID 1). Al reiniciar, marcarlo como INTERRUPTED sería un estado imposible:
diría "interrumpido" mientras el proceso sigue vivo.

Solución: al lanzar cada trabajo se guarda su "huella":
  - pid
  - inicio_proceso: momento en que el kernel creó el proceso (campo 22 de
    /proc/<pid>/stat, en ticks desde el arranque del sistema)
  - boot_id: identificador del arranque actual del sistema

Al reiniciar, por cada trabajo que estaba "En ejecución" se revisa si existe un
proceso con ese pid, el mismo inicio_proceso y el mismo boot_id. Solo si las
tres coinciden es el mismo proceso. Así nunca se mata a un proceso ajeno que
reutilizó el pid. Si es el mismo, se le aplica la política de escalamiento
(SIGTERM al grupo -> gracia -> SIGKILL) y se espera a que desaparezca. Solo
entonces se marca INTERRUPTED.
"""

import os
import signal
import time

RUTA_BOOT_ID = "/proc/sys/kernel/random/boot_id"
MOTIVO_HUERFANO = "recuperación: proceso huérfano detenido"
MOTIVO_CAIDA = "recuperación: Q-umplidor se cerró sin detenerlo"


def _leer(ruta):
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return archivo.read().strip()
    except OSError:
        return None


def _stat(pid):
    """Devuelve (estado, inicio_proceso) del pid, o None si no existe."""
    contenido = _leer(f"/proc/{pid}/stat")
    if contenido is None:
        return None
    # El nombre del programa va entre paréntesis y puede tener espacios;
    # los campos se cuentan después del último ')'.
    campos = contenido.rsplit(")", 1)[1].split()
    return campos[0], int(campos[19])  # campo 3 (estado) y campo 22 (inicio)


def huella_proceso(pid):
    """Identifica un proceso de forma única en este arranque del sistema."""
    if os.name != "posix":
        return None
    datos = _stat(pid)
    if datos is None:
        return None
    return {"pid": pid, "inicio_proceso": datos[1], "boot_id": _leer(RUTA_BOOT_ID)}


def sigue_vivo(huella):
    """True si el proceso de la huella sigue corriendo (y no es otro con el mismo pid)."""
    if not huella or os.name != "posix":
        return False
    if huella.get("boot_id") != _leer(RUTA_BOOT_ID):
        return False  # el sistema se reinició: ningún proceso anterior existe
    datos = _stat(huella["pid"])
    if datos is None:
        return False
    estado, inicio = datos
    # Un zombi (Z) o muerto (X) ya no corre; solo falta que su padre lo recoja.
    return inicio == huella["inicio_proceso"] and estado not in ("Z", "X")


def _senal_grupo(pid, senal):
    try:
        os.killpg(pid, senal)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, senal)
        except (ProcessLookupError, PermissionError):
            pass


def _esperar_fin(huella, segundos):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if not sigue_vivo(huella):
            return True
        time.sleep(0.05)
    return not sigue_vivo(huella)


def detener_huerfano(huella, gracia):
    """Escalamiento para un proceso que ya no es hijo de Q-umplidor.

    No se puede usar wait() porque ahora su padre es el PID 1, que lo
    recolecta. Por eso se revisa /proc hasta que desaparezca.
    Devuelve "SIGTERM", "SIGKILL" o None si ya no estaba vivo.
    """
    if not sigue_vivo(huella):
        return None
    _senal_grupo(huella["pid"], signal.SIGTERM)
    if _esperar_fin(huella, gracia):
        return "SIGTERM"
    _senal_grupo(huella["pid"], signal.SIGKILL)
    _esperar_fin(huella, 5)
    return "SIGKILL"


def recuperar_trabajos(trabajos, gracia):
    """Cierra los trabajos que quedaron "En ejecución" de una sesión anterior.

    Devuelve los mensajes que se muestran al usuario al arrancar.
    """
    mensajes = []
    for id_trabajo, trabajo in trabajos.items():
        if trabajo["estado"] != "En ejecución":
            continue
        senal = detener_huerfano(trabajo.get("huella"), gracia)
        if senal is not None:
            trabajo["senal_final"] = senal
            trabajo["motivo_fin"] = MOTIVO_HUERFANO
            mensajes.append(
                f"Recuperación: el trabajo [{id_trabajo}] seguía corriendo sin supervisión "
                f"(pid {trabajo['huella']['pid']}); se detuvo con {senal}."
            )
        else:
            trabajo["motivo_fin"] = trabajo.get("motivo_fin") or MOTIVO_CAIDA
        trabajo["estado"] = "Interrumpido"
        trabajo["fin"] = time.time()
    return mensajes
