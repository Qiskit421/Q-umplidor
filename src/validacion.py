"""Reglas de validación de solicitudes (RF-02, RNF-14)."""

LONGITUD_MAXIMA = 1024


def validar_solicitud(entrada):
    """Devuelve None si la solicitud es válida, o el motivo del rechazo."""
    if not entrada.strip():
        return "solicitud vacía. Escribe un comando; usa help para ver la lista."
    if len(entrada) > LONGITUD_MAXIMA:
        return f"solicitud demasiado larga (máximo {LONGITUD_MAXIMA} caracteres)."
    if any(ord(c) < 32 and c != "\t" for c in entrada):
        return "la solicitud contiene caracteres de control no permitidos."
    return None