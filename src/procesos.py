import sys
from pathlib import Path

print("[INFO] Iniciando la verificacion de procesos de Linux...")
print("[INFO] Proceso PID 1024: ejecucion completada correctamente.")
print("[INFO] Proceso PID 1100 (ls): archivos de la carpeta listados correctamente.")
print("[INFO] Proceso PID 1200 (mkdir): carpeta 'tareas' creada correctamente.")
print("[INFO] Proceso PID 1300 (cp): archivo 'notas.txt' copiado correctamente.")
print("[INFO] Proceso PID 1400 (mv): archivo 'foto.png' movido correctamente.")
print("[INFO] Proceso PID 1500 (echo): mensaje mostrado correctamente.")

archivo = Path("procesos_activos.txt")
hubo_error = False

print("[ERROR] Proceso PID 2100 (cat): el archivo 'datos.txt' no existe.", file=sys.stderr)
print("[ERROR] Proceso PID 2200 (cd): la carpeta 'documentos' no existe.", file=sys.stderr)
print("[ERROR] Proceso PID 2300 (rm): permiso denegado para borrar 'sistema.txt'.", file=sys.stderr)
hubo_error = True

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
