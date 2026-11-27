"""Reglas del cierre controlado del servicio (RF-15)."""


def es_envio_de_trabajo(partes):
    """True si el comando crea un trabajo nuevo (y por eso se rechaza durante el cierre)."""
    if not partes:
        return False
    if partes[0] == "ejecutar":
        return True
    if partes[0] == "sleep":
        return partes[-1] == "&"  # "sleep 5" en primer plano no crea ningún trabajo
    if partes[0] == "queue":
        return len(partes) > 1 and partes[1] not in ("clear", "cancelar")
    return False