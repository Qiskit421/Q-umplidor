"""Límite configurable de concurrencia (RF-05).

Decide cuántos trabajos pueden estar en ejecución al mismo tiempo. Si ya se
alcanzó el límite, los trabajos nuevos esperan en la cola (estado QUEUED)
hasta que alguno termine.

Configuración:
  - Al arrancar, con la variable de entorno Q_LIMITE_CONCURRENCIA
      Q_LIMITE_CONCURRENCIA=3 python3 src/main.py
  - Durante la sesión, con el comando:
      limite        -> muestra el límite y cuántos trabajos ocupan lugar
      limite <N>    -> cambia el límite a N (entero >= 1)

Bajar el límite no detiene trabajos que ya están corriendo: solo impide que
arranquen nuevos hasta que la cantidad en ejecución baje del nuevo límite.
"""

import os

VARIABLE_LIMITE = "Q_LIMITE_CONCURRENCIA"
LIMITE_POR_DEFECTO = 2


def validar_limite(valor):
    """Convierte el texto a un límite válido (entero >= 1). Devuelve None si no lo es."""
    try:
        limite = int(valor)
    except (TypeError, ValueError):
        return None
    return limite if limite >= 1 else None


def leer_limite_concurrencia():
    """Lee el límite inicial desde Q_LIMITE_CONCURRENCIA (por defecto 2)."""
    valor = os.environ.get(VARIABLE_LIMITE, str(LIMITE_POR_DEFECTO))
    limite = validar_limite(valor)
    if limite is None:
        raise SystemExit(
            f"{VARIABLE_LIMITE} debe ser un entero mayor o igual a 1 (se recibió '{valor}')"
        )
    return limite


class ControlConcurrencia:
    """Guarda el límite y responde si hay lugar para arrancar otro trabajo.

    No lleva su propio contador: recibe una función que cuenta los trabajos
    activos revisando los procesos reales. Así, si un trabajo termina y nadie
    lo ha consultado, su lugar se libera igual, y el contador nunca se
    desincroniza por un error al sumar o restar.
    """

    def __init__(self, limite, contar_activos):
        self._limite = limite
        self._contar_activos = contar_activos

    @property
    def limite(self):
        return self._limite

    def cambiar_limite(self, nuevo):
        self._limite = nuevo

    def activos(self):
        return self._contar_activos()

    def hay_espacio(self):
        """True si los trabajos que ocupan lugar son menos que el límite."""
        return self.activos() < self._limite


def atender_comando_limite(partes, control, al_cambiar):
    """Comando de consola: 'limite' o 'limite <N>'.

    al_cambiar() se llama después de cambiar el límite, para despertar al
    despachador de la cola y que arranque trabajos si ahora hay lugar.
    """
    if len(partes) == 1:
        print(
            f"Límite de concurrencia: {control.limite} "
            f"(ocupados ahora: {control.activos()})"
        )
        return
    if len(partes) != 2:
        print("limite: argumentos incorrectos. Uso: limite o limite <N>")
        return
    nuevo = validar_limite(partes[1])
    if nuevo is None:
        print("limite: el límite debe ser un entero mayor o igual a 1")
        return
    anterior = control.limite
    control.cambiar_limite(nuevo)
    al_cambiar()
    print(f"Límite de concurrencia: {anterior} -> {nuevo}")
    if control.activos() > nuevo:
        print(
            "limite: hay más trabajos corriendo que el nuevo límite; "
            "no se detienen, pero no arrancará ninguno hasta que bajen."
        )
