import sys
from pathlib import Path

print("[INFO] Iniciando la verificacion de procesos de Linux...")
print("[INFO] Proceso PID 1024: ejecucion completada correctamente.")

archivo = Path("procesos_activos.txt")
hubo_error = False

try:
    contenido = archivo.read_text(encoding="utf-8")
    print("[INFO] Archivo de procesos cargado correctamente.")
except FileNotFoundError:
    print(
        f"[ERROR] No se pudo leer '{archivo.name}': archivo no encontrado.",
        file=sys.stderr,
    )
    hubo_error = True

print("[INFO] Verificacion de procesos finalizada.")

sys.exit(1 if hubo_error else 0)
