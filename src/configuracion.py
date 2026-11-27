"""Configuración del servicio (RF-16)."""
import os
from pathlib import Path


def leer_directorio_datos(por_defecto, entorno=None):
    """Directorio de datos: Q_DIRECTORIO_DATOS o, si no está definida, el predeterminado.

    Se crea si no existe y se comprueba que se pueda escribir. Si no se puede
    usar, termina con un mensaje claro en lugar de fallar más adelante.
    """
    entorno = os.environ if entorno is None else entorno
    valor = entorno.get("Q_DIRECTORIO_DATOS", "").strip()
    ruta = (Path(valor).expanduser() if valor else Path(por_defecto)).resolve()
    if ruta.exists() and not ruta.is_dir():
        raise SystemExit(f"Q_DIRECTORIO_DATOS: '{ruta}' existe pero no es una carpeta")
    try:
        ruta.mkdir(parents=True, exist_ok=True)
        prueba = ruta / ".escritura"  # comprueba que se pueda escribir
        prueba.touch()
        prueba.unlink()
    except OSError as error:
        raise SystemExit(f"Q_DIRECTORIO_DATOS: no se puede usar '{ruta}' ({error.strerror})")
    return ruta