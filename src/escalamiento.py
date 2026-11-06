"""Política de escalamiento para trabajos que no terminan (RF-30).

Cuando hay que detener un trabajo (porque el usuario lo canceló, porque
superó el tiempo máximo o porque Q-umplidor se está cerrando):

  1. Se envía SIGTERM a todo el grupo de procesos del trabajo, para que
     termine ordenadamente (cerrar archivos, limpiar, etc.).
  2. Se espera un periodo de gracia (por defecto 2 s).
  3. Si sigue vivo, se envía SIGKILL, que no se puede ignorar.
  4. Se recolecta el proceso con wait() para que no quede como zombi.

Se manda la señal al GRUPO y no solo al proceso porque un trabajo lanzado con
el shell (por ejemplo "queue sleep 100; echo fin") tiene hijos propios. Si
solo se matara a bash, el sleep quedaría huérfano corriendo. Por eso
lanzar_trabajo() arranca cada trabajo con start_new_session=True: el trabajo
queda como líder de su propio grupo y os.killpg() alcanza a todos sus hijos.

Configuración (variables de entorno al arrancar):
  Q_GRACIA_SIGTERM   segundos entre SIGTERM y SIGKILL (por defecto 2)
  Q_TIEMPO_MAXIMO    segundos que puede durar un trabajo en RUNNING antes de
                     detenerlo con esta misma política (0 = sin límite, por defecto)

Comando de consola:
  politica           muestra la configuración vigente
"""

import os
import signal
import subprocess
import threading
import time

from estados import MOTIVO_TIEMPO_MAXIMO, MOTIVO_USUARIO

VARIABLE_GRACIA = "Q_GRACIA_SIGTERM"
VARIABLE_TIEMPO_MAXIMO = "Q_TIEMPO_MAXIMO"
GRACIA_POR_DEFECTO = 2.0
TIEMPO_MAXIMO_POR_DEFECTO = 0.0  # 0 = desactivado
INTERVALO_VIGILANCIA = 0.5


def _leer_segundos(variable, por_defecto, minimo):
    valor = os.environ.get(variable, str(por_defecto))
    try:
        segundos = float(valor)
        if segundos < minimo:
            raise ValueError
    except ValueError:
        raise SystemExit(f"{variable} debe ser un número mayor o igual a {minimo} (se recibió '{valor}')")
    return segundos


class Politica:
    def __init__(self, gracia, tiempo_maximo):
        self.gracia = gracia
        self.tiempo_maximo = tiempo_maximo  # 0 = sin límite


def leer_politica():
    """Lee la política desde las variables de entorno."""
    return Politica(
        gracia=_leer_segundos(VARIABLE_GRACIA, GRACIA_POR_DEFECTO, 0.1),
        tiempo_maximo=_leer_segundos(VARIABLE_TIEMPO_MAXIMO, TIEMPO_MAXIMO_POR_DEFECTO, 0),
    )


_envio_externo = None


def usar_envio_de_senales(funcion):
    """main.py registra aquí su propio enviar_senal(proceso, forzar).

    Así el escalamiento y el resto del programa mandan las señales de la misma
    forma (grupo de procesos en Linux/WSL, Job Object en Windows).
    """
    global _envio_externo
    _envio_externo = funcion


def _enviar_senal(proceso, forzar):
    """Manda SIGTERM (o SIGKILL si forzar) al grupo del trabajo."""
    if _envio_externo is not None:
        _envio_externo(proceso, forzar=forzar)
        return
    if os.name != "posix":
        # Windows no tiene grupos POSIX ni SIGKILL; se usa lo que ofrece Popen.
        proceso.kill() if forzar else proceso.terminate()
        return
    senal = signal.SIGKILL if forzar else signal.SIGTERM
    try:
        os.killpg(proceso.pid, senal)
    except (ProcessLookupError, PermissionError):
        # El trabajo no es líder de grupo (o el grupo ya no existe):
        # se le manda la señal solo al proceso.
        try:
            proceso.send_signal(senal)
        except ProcessLookupError:
            pass


def terminar_con_escalamiento(proceso, gracia):
    """Aplica SIGTERM -> espera -> SIGKILL a un proceso.

    Devuelve "SIGTERM" si terminó durante la gracia, "SIGKILL" si hubo que
    forzarlo, o None si el proceso ya había terminado solo.
    """
    if proceso.poll() is not None:
        return None
    _enviar_senal(proceso, forzar=False)
    try:
        proceso.wait(timeout=gracia)
        return "SIGTERM"
    except subprocess.TimeoutExpired:
        _enviar_senal(proceso, forzar=True)
        proceso.wait()
        return "SIGKILL"


def detener_trabajo(trabajo, politica, motivo=MOTIVO_USUARIO):
    """Detiene un trabajo en ejecución y anota cómo terminó.

    Solo marca 'cancelado' si lo pidió el usuario; si fue por tiempo máximo,
    estados.estado_final() lo dejará como FAILED.
    """
    proceso = trabajo.get("proceso")
    if proceso is None:
        return None
    trabajo["motivo_fin"] = motivo
    if motivo == MOTIVO_USUARIO:
        trabajo["cancelado"] = True
    senal = terminar_con_escalamiento(proceso, politica.gracia)
    if senal is not None:
        trabajo["senal_final"] = senal
    return senal


def iniciar_vigilante(politica, trabajos_en_ejecucion, al_detener, debe_parar):
    """Hilo que detiene los trabajos que superan Q_TIEMPO_MAXIMO.

    trabajos_en_ejecucion() devuelve [(id, trabajo), ...] con proceso vivo.
    al_detener(id, trabajo, senal) se llama después de detener cada uno.
    No hace nada si el tiempo máximo es 0.
    """
    if politica.tiempo_maximo <= 0:
        return None

    def vigilar():
        while not debe_parar():
            ahora = time.time()
            for id_trabajo, trabajo in trabajos_en_ejecucion():
                inicio = trabajo.get("inicio")
                if inicio is None or trabajo.get("motivo_fin"):
                    continue  # todavía arrancando, o ya se está deteniendo
                if ahora - inicio > politica.tiempo_maximo:
                    # Un hilo por trabajo, para que la gracia de uno no
                    # retrase la revisión de los demás.
                    def detener(i=id_trabajo, t=trabajo):
                        senal = detener_trabajo(t, politica, MOTIVO_TIEMPO_MAXIMO)
                        al_detener(i, t, senal)
                    trabajo["motivo_fin"] = MOTIVO_TIEMPO_MAXIMO
                    threading.Thread(target=detener, daemon=True).start()
            time.sleep(INTERVALO_VIGILANCIA)

    hilo = threading.Thread(target=vigilar, daemon=True)
    hilo.start()
    return hilo


def mostrar_politica(politica):
    print("Política de escalamiento:")
    print(f"  1. SIGTERM al grupo de procesos del trabajo")
    print(f"  2. Gracia: {politica.gracia:g}s ({VARIABLE_GRACIA})")
    print(f"  3. SIGKILL si sigue vivo, y wait() para no dejar zombis")
    if politica.tiempo_maximo > 0:
        print(f"  Tiempo máximo por trabajo: {politica.tiempo_maximo:g}s ({VARIABLE_TIEMPO_MAXIMO}); "
              f"al superarlo se detiene y queda FAILED")
    else:
        print(f"  Tiempo máximo por trabajo: sin límite ({VARIABLE_TIEMPO_MAXIMO}=0)")
