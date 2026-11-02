#!/usr/bin/env python3
"""
verif/scripts/test_avance1_completo.py — Q-umplidor

Script inicial de verificación funcional para el Avance 1.
"""

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_PY = REPO_ROOT / "src" / "main.py"

resultados = []  # (nombre, estado) con estado en {"PASS", "FAIL", "NO IMPLEMENTADO"}


def registrar(nombre, estado, detalle=""):
    resultados.append((nombre, estado))
    marca = {"PASS": "PASS", "FAIL": "FAIL", "NO IMPLEMENTADO": "N/I "}[estado]
    linea = f"[{marca}] {nombre}"
    if detalle:
        linea += f" — {detalle}"
    print(linea)


def no_reconocido(salida, comando):
    """True si main.py respondió con su mensaje de 'comando no reconocido'
    para la primera palabra de ese comando (es decir, no existe todavía)."""
    primera_palabra = comando.split()[0]
    return f"{primera_palabra}: comando no reconocido" in salida


class Sesion:
    """Envuelve una sesión interactiva de src/main.py para poder enviar
    comandos uno por uno y revisar la salida acumulada hasta ese momento."""

    def __init__(self):
        self.proceso = subprocess.Popen(
            [sys.executable, str(MAIN_PY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._offset = 0

    def enviar(self, comando, espera=0.3):
        self.proceso.stdin.write(comando + "\n")
        self.proceso.stdin.flush()
        time.sleep(espera)

    def cerrar(self, espera_final=0.0):
        if espera_final:
            time.sleep(espera_final)
        try:
            self.proceso.stdin.close()
        except Exception:
            pass
        try:
            salida, _ = self.proceso.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.proceso.kill()
            salida, _ = self.proceso.communicate()
        return salida


def main():
    if not MAIN_PY.exists():
        print(f"No se encontró {MAIN_PY}; nada que verificar.")
        sys.exit(1)

    print(f"Verificando: {MAIN_PY.relative_to(REPO_ROOT)}\n")
    sesion = Sesion()

    # --- 1/2/3: enviar un trabajo, ID único, proceso separado (no bloqueante) ---
    inicio = time.time()
    sesion.enviar("sleep 3 &", espera=0.3)
    transcurrido_envio = time.time() - inicio

    sesion.enviar("sleep 1 &", espera=0.3)
    sesion.enviar("listar")

    # --- 4: consultar el estado de un trabajo por su ID ---
    sesion.enviar("estado 1")

    # --- 5: ya se mandó 'listar' arriba; se vuelve a pedir tras avanzar el tiempo ---
    sesion.enviar("listar")

    # --- 6: solicitar la cancelación de un trabajo en ejecución ---
    sesion.enviar("cancelar 1")

    # --- 7: código de salida mientras corre y, más adelante, ya terminado ---
    sesion.enviar("codigo 1")

    # --- 8: comando inválido no debe tumbar el servicio ---
    sesion.enviar("comando_invalido_de_prueba")
    sesion.enviar("listar")

    time.sleep(3.2)
    # El trabajo 1 se canceló arriba (su código es 143, por SIGTERM); el que
    # termina normal es el 2 ("sleep 1 &"), que debe informar código 0.
    sesion.enviar("codigo 2")
    sesion.enviar("listar")

    salida = sesion.cerrar()

    print("--- Salida completa capturada (evidencia) ---")
    print(salida)
    print("--- Fin de la salida ---\n")

    # ===================== 1. Enviar un trabajo =====================
    if "ID: [1]" in salida:
        registrar("1. Enviar un trabajo", "PASS", "'sleep 3 &' fue aceptado y devolvió un ID")
    else:
        registrar("1. Enviar un trabajo", "FAIL", "no se encontró 'ID: [1]' en la salida")

    # ===================== 2. Obtener un identificador único =====================
    if "ID: [1]" in salida and "ID: [2]" in salida:
        registrar("2. Obtener un identificador único", "PASS", "dos trabajos recibieron IDs distintos y consecutivos (1 y 2)")
    else:
        registrar("2. Obtener un identificador único", "FAIL", "no se asignaron IDs distintos a los dos trabajos enviados")

    # ===================== 3. Ejecutarlo como un proceso separado =====================
    if transcurrido_envio < 2.0:
        registrar(
            "3. Ejecutarlo como un proceso separado",
            "PASS",
            f"'sleep 3 &' devolvió el control en {transcurrido_envio:.2f}s (no bloqueó la consola)",
        )
    else:
        registrar(
            "3. Ejecutarlo como un proceso separado",
            "FAIL",
            f"tardó {transcurrido_envio:.2f}s; parece estar bloqueando en vez de correr aparte",
        )

    # ===================== 4. Consultar el estado =====================
    if no_reconocido(salida, "estado 1"):
        registrar(
            "4. Consultar el estado",
            "NO IMPLEMENTADO",
            "main.py no reconoce todavía un comando 'estado <id>' (RF-08); "
            "hoy el estado solo se ve indirectamente dentro de 'listar'",
        )
    elif "En ejecución" in salida or "Terminado" in salida or "Falló" in salida:
        registrar("4. Consultar el estado", "PASS", "'estado 1' devolvió un estado reconocible")
    else:
        registrar("4. Consultar el estado", "FAIL", "'estado 1' no devolvió un estado reconocible")

    # ===================== 5. Listar trabajos =====================
    tiene_encabezado = "ESTADO" in salida and "COMANDO" in salida
    tiene_ambos_jobs = ("1" in salida and "sleep 3 &" in salida) and ("2" in salida and "sleep 1 &" in salida)
    if tiene_encabezado and tiene_ambos_jobs:
        registrar("5. Listar trabajos", "PASS", "'listar' mostró ambos trabajos con encabezado y estado")
    else:
        registrar("5. Listar trabajos", "FAIL", "'listar' no mostró correctamente los trabajos enviados")

    # ===================== 6. Solicitar su cancelación =====================
    if no_reconocido(salida, "cancelar 1"):
        registrar(
            "6. Solicitar su cancelación",
            "NO IMPLEMENTADO",
            "main.py no reconoce todavía un comando 'cancelar <id>' (RF-10)",
        )
    else:
        confirma_cancelacion = "cancelad" in salida.lower()
        registrar(
            "6. Solicitar su cancelación",
            "PASS" if confirma_cancelacion else "FAIL",
            "" if confirma_cancelacion else "'cancelar 1' no confirmó la cancelación en la salida",
        )

    # ===================== 7. Obtener su código de salida =====================
    informa_en_ejecucion = "todavía está en ejecución" in salida
    informa_codigo_final = "el trabajo [2] terminó con código de salida 0" in salida
    if informa_en_ejecucion and informa_codigo_final:
        registrar(
            "7. Obtener su código de salida",
            "PASS",
            "'codigo' informó primero que seguía en ejecución y después el código final (0)",
        )
    elif informa_codigo_final:
        registrar("7. Obtener su código de salida", "PASS", "'codigo 2' informó el código de salida final (0)")
    else:
        registrar("7. Obtener su código de salida", "FAIL", "'codigo 2' no informó el código de salida 0 del trabajo que terminó normal")

    # ===================== 8. Manejar comandos inválidos sin terminar el servicio =====================
    responde_invalido = "comando_invalido_de_prueba: comando no reconocido" in salida
    sigue_viva_tras_invalido = salida.count("ESTADO") >= 2
    if responde_invalido and sigue_viva_tras_invalido:
        registrar(
            "8. Manejar comandos inválidos sin terminar el servicio",
            "PASS",
            "el comando inválido se reportó como error controlado y el servicio siguió respondiendo después",
        )
    else:
        registrar(
            "8. Manejar comandos inválidos sin terminar el servicio",
            "FAIL",
            "no se confirmó el manejo correcto del comando inválido",
        )

    # ===================== Resumen =====================
    print("\n=== Resumen ===")
    pasados = [n for n, e in resultados if e == "PASS"]
    fallidos = [n for n, e in resultados if e == "FAIL"]
    pendientes = [n for n, e in resultados if e == "NO IMPLEMENTADO"]

    print(f"PASS: {len(pasados)}/{len(resultados)}")
    print(f"FAIL: {len(fallidos)}/{len(resultados)}")
    print(f"NO IMPLEMENTADO: {len(pendientes)}/{len(resultados)}")

    if pendientes:
        print("\nPuntos del Avance 1 que todavía faltan implementar en src/main.py:")
        for n in pendientes:
            print(f"  - {n}")

    if fallidos:
        print("\nPuntos implementados pero que fallaron la verificación:")
        for n in fallidos:
            print(f"  - {n}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
