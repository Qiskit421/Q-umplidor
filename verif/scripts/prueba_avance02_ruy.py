#!/usr/bin/env python3
"""Verificación del Avance 02 — concurrencia, estados, escalamiento y recuperación.

Casos (definidos en verif/test-cases/casos-de-prueba.md):
  TC-020  Límite de concurrencia (RF-05)
  TC-021  Estados y tiempos coherentes (RF-06)
  TC-022  Escalamiento SIGTERM -> SIGKILL sin huérfanos (RF-30, RF-10)
  TC-023  Tiempo máximo por trabajo (RF-30)
  TC-024  Proceso hijo terminado desde fuera (robustez)
  TC-025  Caída abrupta de Q-umplidor (kill -9) y recuperación (RF-13)
  TC-026  Cierre por SIGTERM / SIGHUP sin huérfanos (RF-13)
  TC-027  Saturación de la cola con el límite lleno (RF-25 + RF-05)

Uso, desde la raíz del repositorio (Linux o WSL):
  python3 verif/scripts/prueba_avance02_ruy.py            # todos los casos
  python3 verif/scripts/prueba_avance02_ruy.py TC-022     # solo algunos

No toca data/ del repositorio: cada caso corre una copia de src/ en una carpeta
temporal. La evidencia queda en verif/results/<caso>-<fecha>/:
  entorno.txt          fecha, commit, sistema y configuración
  salida_consola.txt   lo que se escribió y lo que respondió Q-umplidor
  verificacion.txt     cada comprobación con PASS o FAIL
  trabajos.json        el archivo de persistencia al terminar el caso
Termina con código 0 solo si todas las comprobaciones pasan.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RESULTADOS = RAIZ / "verif" / "results"
FECHA = datetime.now().strftime("%Y%m%d")
TERCO = ("python3 -c 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
         "time.sleep(600)'")


# ------------------------------------------------------------------ apoyo

def procesos():
    """[(pid, ppid, pgid, estado, comando)] de todos los procesos del sistema."""
    salida = subprocess.run(["ps", "-eo", "pid=,ppid=,pgid=,stat=,args="],
                            capture_output=True, text=True).stdout
    filas = []
    for linea in salida.splitlines():
        partes = linea.split(None, 4)
        if len(partes) == 5:
            filas.append((int(partes[0]), int(partes[1]), int(partes[2]), partes[3], partes[4]))
    return filas


def vivos_de_grupos(pgids):
    """Procesos que siguen corriendo (no zombis) en los grupos dados."""
    return [p for p in procesos() if p[2] in pgids and not p[3].startswith("Z")]


def grupos_de_hijos(pid):
    """Grupos de procesos de los trabajos (hijos directos de Q-umplidor), vistos con ps."""
    return {p[2] for p in procesos() if p[1] == pid}


def pid_hijo(pid_padre, termina_en):
    """PID del proceso hijo de Q-umplidor cuyo comando termina con el texto dado."""
    for p in procesos():
        if p[1] == pid_padre and p[4].rstrip().endswith(termina_en):
            return p[0]
    return None


def zombis_hijos_de(pid):
    return [p for p in procesos() if p[1] == pid and p[3].startswith("Z")]


class QUmplidor:
    """Corre Q-umplidor con una copia de src/ y le escribe comandos."""

    def __init__(self, caso, carpeta, env=None, limpiar=True):
        self.caso, self.carpeta = caso, carpeta
        if limpiar:
            shutil.rmtree(carpeta, ignore_errors=True)
            shutil.copytree(RAIZ / "src", carpeta / "src",
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.env = env or {}
        self.p = subprocess.Popen(
            [sys.executable, "-u", "src/main.py"], cwd=carpeta,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=dict(os.environ, **self.env))
        self.lineas = []
        threading.Thread(target=self._leer, daemon=True).start()
        time.sleep(0.4)

    def _leer(self):
        for linea in iter(self.p.stdout.readline, ""):
            self.lineas.append(linea.replace("Q-umplidor> ", ""))

    def cmd(self, texto, espera=0.3):
        self.lineas.append(f">>> {texto}\n")
        self.p.stdin.write(texto + "\n")
        self.p.stdin.flush()
        time.sleep(espera)

    def esperar(self, texto, limite=15):
        """Espera hasta que Q-umplidor imprima el texto. Devuelve True si apareció."""
        fin = time.time() + limite
        while time.time() < fin:
            if texto in self.salida():
                return True
            time.sleep(0.02)
        return False

    def nota(self, texto):
        self.lineas.append(f"### {texto}\n")

    def salida(self):
        return "".join(self.lineas)

    def salir(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        self.p.wait(timeout=60)
        time.sleep(0.2)

    def datos(self):
        ruta = self.carpeta / "data" / "trabajos.json"
        return {t["id"]: t for t in json.loads(ruta.read_text(encoding="utf-8"))["trabajos"]}


class Caso:
    def __init__(self, id_caso, titulo, requisitos, env):
        self.id, self.titulo, self.requisitos, self.env = id_caso, titulo, requisitos, env
        self.chequeos = []
        self.consola = []
        self.tmp = Path(tempfile.mkdtemp(prefix=f"qumplidor-{id_caso}-"))

    def check(self, descripcion, ok, detalle=""):
        self.chequeos.append((bool(ok), descripcion, detalle))

    def guardar(self, q):
        self.consola.append(q.salida())

    def escribir(self):
        carpeta = RESULTADOS / f"{self.id}-{FECHA}"
        carpeta.mkdir(parents=True, exist_ok=True)
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ,
                                capture_output=True, text=True).stdout.strip() or "sin git"
        sucio = subprocess.run(["git", "status", "--porcelain", "src"], cwd=RAIZ,
                               capture_output=True, text=True).stdout.strip()
        (carpeta / "entorno.txt").write_text(
            f"Caso: {self.id} — {self.titulo} ({self.requisitos})\n"
            f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n"
            f"Commit: {commit}{' (con cambios sin commit en src/)' if sucio else ''}\n"
            f"Entorno: {os.uname().sysname} {os.uname().release}, Python {sys.version.split()[0]}\n"
            f"Configuración: {self.env or 'valores por defecto'}\n", encoding="utf-8")
        (carpeta / "salida_consola.txt").write_text("\n".join(self.consola), encoding="utf-8")
        texto = [f"{'PASS' if ok else 'FAIL'}  {d}" + (f"  [{x}]" if x else "")
                 for ok, d, x in self.chequeos]
        resultado = "PASS" if all(ok for ok, _, _ in self.chequeos) else "FAIL"
        texto.append(f"\nRESULTADO {self.id}: {resultado}")
        (carpeta / "verificacion.txt").write_text("\n".join(texto) + "\n", encoding="utf-8")
        json_final = self.tmp / "data" / "trabajos.json"
        if json_final.exists():
            shutil.copy(json_final, carpeta / "trabajos.json")
        shutil.rmtree(self.tmp, ignore_errors=True)
        return resultado, carpeta, texto


def sin_restos(caso, q, nombre="al terminar"):
    """Comprobación común: ni zombis ni archivos abiertos de data/."""
    caso.check(f"Sin procesos zombi hijos de Q-umplidor ({nombre})", not zombis_hijos_de(q.p.pid))
    try:
        abiertos = [f for f in os.listdir(f"/proc/{q.p.pid}/fd")
                    if "/data/" in os.path.realpath(f"/proc/{q.p.pid}/fd/{f}")]
    except OSError:
        abiertos = []
    caso.check(f"Q-umplidor no deja archivos de data/ abiertos ({nombre})", not abiertos, abiertos)


# ------------------------------------------------------------------ casos

def tc020():
    c = Caso("TC-020", "Límite configurable de concurrencia", "RF-05",
             {"Q_LIMITE_CONCURRENCIA": "2"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("limite")
    for comando in ["sleep 2 &", "sleep 2 &", "sleep 2 &", "queue sleep 2", "ejecutar echo hola &"]:
        q.cmd(comando, 0.1)
    maximo, muestras = 0, 0
    fin = time.time() + 6.5
    while time.time() < fin:  # cuenta procesos reales hijos de Q-umplidor
        hijos = [p for p in procesos() if p[1] == q.p.pid and not p[3].startswith("Z")]
        maximo, muestras = max(maximo, len(hijos)), muestras + 1
        time.sleep(0.05)
    q.cmd("listar")
    q.cmd("limite 3")
    q.cmd("limite 0")
    q.cmd("limite x")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    c.check("Nunca hubo más de 2 procesos de trabajos a la vez", maximo <= 2,
            f"máximo observado {maximo} en {muestras} muestras")
    c.check("Sí hubo 2 trabajos en paralelo (no se serializó)", maximo == 2)
    c.check("El tercer trabajo con & se envió a la cola por el límite",
            "Límite de concurrencia alcanzado (2)" in s)
    c.check("Los 5 trabajos terminaron SUCCEEDED", all(t["estado"] == "Terminado" for t in d.values()),
            {i: t["estado"] for i, t in d.items()})
    inicio = {i: t["inicio"] for i, t in d.items()}
    c.check("Los encolados arrancan en orden de llegada (FIFO)", inicio[3] <= inicio[4] <= inicio[5])
    c.check("Los encolados esperaron a que terminara uno de los primeros",
            inicio[3] >= min(d[1]["fin"], d[2]["fin"]) - 0.3)
    c.check("limite 3 cambia el límite en caliente", "Límite de concurrencia: 2 -> 3" in s)
    c.check("limite 0 y limite x se rechazan", s.count("debe ser un entero mayor o igual a 1") == 2)
    return c


def tc021():
    c = Caso("TC-021", "Estados y tiempos coherentes", "RF-06",
             {"Q_LIMITE_CONCURRENCIA": "1", "Q_GRACIA_SIGTERM": "1"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("sleep 2 &", 0.2)                      # 1 SUCCEEDED
    q.cmd("ejecutar bash -c 'exit 3' &", 0.2)    # 2 QUEUED -> FAILED
    q.cmd("queue sleep 30", 0.2)                 # 3 QUEUED -> CANCELED en cola
    q.cmd("listar", 0.2)
    estados_en_cola = q.salida()
    q.cmd("cancelar 3", 0.2)
    time.sleep(2.5)
    q.cmd("listar")
    q.cmd("estado 2")
    q.cmd("codigo 2")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    c.check("Se muestra QUEUED mientras espera por el límite", " QUEUED " in estados_en_cola)
    c.check("Se muestra RUNNING mientras corre", " RUNNING " in estados_en_cola)
    c.check("Código 0 -> SUCCEEDED", d[1]["estado"] == "Terminado" and " SUCCEEDED " in s)
    c.check("Código 3 -> FAILED y codigo informa 3",
            d[2]["estado"].startswith("Falló") and "código de salida 3" in s)
    c.check("Cancelado en cola -> CANCELED sin haber arrancado",
            d[3]["estado"] == "Cancelado" and d[3]["inicio"] is None)
    for i, t in d.items():
        envio = t.get("momento_encolado") or t["inicio"]
        orden = [x for x in (envio, t["inicio"], t["fin"]) if x is not None]
        c.check(f"Trabajo {i}: envío <= inicio <= fin", orden == sorted(orden))
    c.check("El trabajo 2 registró tiempo de espera en cola (>= 1 s)",
            d[2]["inicio"] - d[2]["momento_encolado"] >= 1)
    c.check("Ningún trabajo quedó en estado no final", all(
        t["estado"] not in ("En ejecución", "En cola") for t in d.values()))
    c.check("estado <id> muestra Enviado, Inicio, Fin, Espera y Ejecución",
            all(k in s for k in ("Enviado:", "Inicio:", "Fin:", "Espera:", "Ejecución:")))
    return c


def tc022():
    c = Caso("TC-022", "Escalamiento SIGTERM -> SIGKILL sin huérfanos", "RF-30, RF-10",
             {"Q_LIMITE_CONCURRENCIA": "5", "Q_GRACIA_SIGTERM": "1"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("sleep 300 &", 0.2)
    q.cmd(f"ejecutar {TERCO} &", 0.2)
    q.cmd("queue sleep 77; echo fin", 0.2)
    q.cmd("ejecutar bash -c 'sleep 88; echo x' &", 0.6)
    q.cmd("politica")
    grupos = grupos_de_hijos(q.p.pid)
    hijos_antes = vivos_de_grupos(grupos)
    q.nota(f"Procesos de los trabajos antes de cancelar: {len(hijos_antes)}")
    q.cmd("cancelar 1", 0)
    q.esperar("Trabajo [1] cancelado")
    t0 = time.time()
    q.cmd("cancelar 2", 0)
    q.esperar("Trabajo [2] cancelado")
    duracion_terco = time.time() - t0
    q.cmd("cancelar 3", 0.1)
    q.cmd("cancelar 4", 0.5)
    q.cmd("codigo 1")
    q.cmd("codigo 2")
    q.cmd("estado 2")
    restos = vivos_de_grupos(grupos)
    q.nota(f"Procesos de los trabajos después de cancelar: {len(restos)}")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    c.check("Antes de cancelar, los trabajos de shell tenían hijos (bash + sleep)",
            len(hijos_antes) >= 6, f"{len(hijos_antes)} procesos")
    c.check("Obediente: terminó con SIGTERM, código 143",
            d[1]["senal_final"] == "SIGTERM" and "código de salida 143" in s)
    c.check("Terco: se forzó con SIGKILL, código 137",
            d[2]["senal_final"] == "SIGKILL" and "código de salida 137" in s)
    c.check("Terco: se esperó la gracia (~1 s) antes de SIGKILL", duracion_terco >= 0.9,
            f"{duracion_terco:.2f}s")
    c.check("Los 4 quedaron CANCELED", all(t["estado"] == "Cancelado" for t in d.values()))
    c.check("Ningún proceso de los trabajos sigue vivo (sin huérfanos)", not restos, restos)
    c.check("motivo_fin y senal_final quedan persistidos",
            all(t.get("motivo_fin") and t.get("senal_final") for t in d.values()))
    return c


def tc023():
    c = Caso("TC-023", "Tiempo máximo por trabajo", "RF-30",
             {"Q_TIEMPO_MAXIMO": "2", "Q_GRACIA_SIGTERM": "1"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("politica")
    q.cmd(f"ejecutar {TERCO} &", 0.1)
    q.cmd("sleep 1 &", 4.5)
    q.cmd("listar")
    q.cmd("estado 1")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    dur = d[1]["fin"] - d[1]["inicio"]
    c.check("El trabajo colgado se detuvo solo y quedó FAILED (tiempo máximo excedido)",
            d[1]["estado"] == "Falló (tiempo máximo excedido)")
    c.check("Se forzó con SIGKILL porque ignoraba SIGTERM", d[1]["senal_final"] == "SIGKILL")
    c.check("Se detuvo entre 2 y 4.5 s (límite + gracia)", 2 <= dur <= 4.5, f"{dur:.2f}s")
    c.check("Un trabajo corto no se ve afectado", d[2]["estado"] == "Terminado")
    c.check("Se avisa en consola", "superó el tiempo máximo" in s)
    return c


def tc024():
    c = Caso("TC-024", "Proceso hijo terminado desde fuera", "robustez, RF-06",
             {"Q_LIMITE_CONCURRENCIA": "3"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("ejecutar sleep 300 &", 0.2)
    q.cmd("queue sleep 301", 0.6)
    pids = {1: pid_hijo(q.p.pid, "sleep 300"), 2: pid_hijo(q.p.pid, "time.sleep(301)")}
    q.nota(f"kill -KILL {pids[1]}  (trabajo 1, desde otra terminal)")
    os.kill(pids[1], signal.SIGKILL)
    q.nota(f"kill -TERM {pids[2]}  (trabajo 2, desde otra terminal)")
    os.kill(pids[2], signal.SIGTERM)
    time.sleep(1)
    zombis = zombis_hijos_de(q.p.pid)  # sin que nadie haya consultado todavía
    q.cmd("listar")
    q.cmd("codigo 1")
    q.cmd("codigo 2")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    c.check("Sin zombis aunque nadie consultó el trabajo", not zombis, zombis)
    c.check("Matado con SIGKILL -> FAILED, código 137",
            d[1]["estado"].startswith("Falló") and "código de salida 137" in s)
    c.check("Matado con SIGTERM -> FAILED, código 143",
            d[2]["estado"].startswith("Falló") and "código de salida 143" in s)
    c.check("No se reportan como CANCELED (nadie pidió cancelar)",
            not any(t["estado"] == "Cancelado" for t in d.values()))
    return c


def tc025():
    c = Caso("TC-025", "Caída abrupta (kill -9) y recuperación", "RF-12, RF-13, RNF-10",
             {"Q_LIMITE_CONCURRENCIA": "3", "Q_GRACIA_SIGTERM": "1"})
    q = QUmplidor(c.id, c.tmp, c.env)
    q.cmd("sleep 600 &", 0.2)
    q.cmd(f"ejecutar {TERCO} &", 0.2)
    q.cmd("queue sleep 601; echo fin", 0.2)
    q.cmd("queue echo recuperado", 0.2)       # 4: espera lugar (límite 3)
    q.cmd("listar", 0.3)
    grupos = grupos_de_hijos(q.p.pid)
    q.nota(f"kill -9 {q.p.pid}  (Q-umplidor muere sin poder limpiar)")
    q.p.kill()
    q.p.wait()
    time.sleep(0.5)
    huerfanos = vivos_de_grupos(grupos)
    q.nota(f"Procesos de trabajos vivos tras la caída: {len(huerfanos)} "
           f"(padres: {sorted({p[1] for p in huerfanos})})")
    c.guardar(q)
    r = QUmplidor(c.id, c.tmp, c.env, limpiar=False)
    time.sleep(3)
    r.cmd("listar")
    r.cmd("estado 2")
    r.cmd("salida 4")
    restos = vivos_de_grupos(grupos)
    sin_restos(c, r, "después de reiniciar")
    r.salir()
    c.guardar(r)
    d, s = r.datos(), r.salida()
    c.check("Tras la caída quedaron procesos huérfanos (el escenario es real)", len(huerfanos) >= 3,
            f"{len(huerfanos)} procesos")
    c.check("Al reiniciar se detuvieron: ningún proceso de los trabajos sigue vivo", not restos, restos)
    c.check("Los 3 que corrían quedaron INTERRUPTED",
            all(d[i]["estado"] == "Interrumpido" for i in (1, 2, 3)))
    c.check("Se registró que eran huérfanos y con qué señal se detuvieron",
            all((d[i].get("motivo_fin") or "").startswith("recuperación") and d[i].get("senal_final")
                for i in (1, 2, 3)))
    c.check("El que ignoraba SIGTERM se forzó con SIGKILL", d[2].get("senal_final") == "SIGKILL")
    c.check("El trabajo en cola no se perdió: se retomó y terminó",
            d[4]["estado"] == "Terminado" and "recuperado" in s)
    c.check("El contador de ID continúa (sin IDs repetidos)", sorted(d) == [1, 2, 3, 4])
    return c


def tc026():
    c = Caso("TC-026", "Cierre por SIGTERM / SIGHUP sin huérfanos", "RF-13",
             {"Q_GRACIA_SIGTERM": "1"})
    for senal in (signal.SIGTERM, signal.SIGHUP):
        q = QUmplidor(c.id, c.tmp, c.env)
        q.cmd("sleep 600 &", 0.2)
        q.cmd(f"ejecutar {TERCO} &", 0.4)
        grupos = grupos_de_hijos(q.p.pid)
        q.nota(f"kill -{senal.name[3:]} {q.p.pid}")
        q.p.send_signal(senal)
        q.p.wait(timeout=20)
        time.sleep(0.3)
        restos = vivos_de_grupos(grupos)
        c.guardar(q)
        d = q.datos()
        # Cierre por señal (cerrar_por_senal): sale con 128 + número de señal (143 / 129).
        c.check(f"{senal.name}: Q-umplidor sale en orden (código {128 + int(senal)})",
                q.p.returncode == 128 + int(senal), q.p.returncode)
        c.check(f"{senal.name}: ningún trabajo queda vivo", not restos, restos)
        c.check(f"{senal.name}: ambos quedan INTERRUPTED con motivo de cierre",
                all(t["estado"] == "Interrumpido" and t.get("motivo_fin") == "cierre de Q-umplidor"
                    for t in d.values()))
    return c


def tc027():
    c = Caso("TC-027", "Saturación de la cola con el límite lleno", "RF-25, RF-05, RNF-29",
             {"Q_LIMITE_CONCURRENCIA": "1", "Q_CAPACIDAD_COLA": "2", "Q_GRACIA_SIGTERM": "1"})
    q = QUmplidor(c.id, c.tmp, c.env)
    for comando in ["sleep 30 &", "sleep 30 &", "queue sleep 30", "queue sleep 30", "sleep 30 &"]:
        q.cmd(comando, 0.2)
    q.cmd("listar")
    sin_restos(c, q)
    q.salir()
    c.guardar(q)
    d, s = q.datos(), q.salida()
    rechazos = s.count("cola llena (2/2 en espera), trabajo rechazado")
    c.check("Los dos envíos extra se rechazan explícitamente", rechazos == 2, rechazos)
    c.check("Un rechazo no anuncia antes que 'se envía a la cola'",
            s.count("se envía a la cola") == 1)
    c.check("Los rechazados no se registran ni consumen ID", sorted(d) == [1, 2, 3])
    c.check("Al salir, los aceptados quedan en estado final",
            all(t["estado"] in ("Interrumpido", "En cola", "Terminado") for t in d.values()))
    return c


CASOS = {"TC-020": tc020, "TC-021": tc021, "TC-022": tc022, "TC-023": tc023,
         "TC-024": tc024, "TC-025": tc025, "TC-026": tc026, "TC-027": tc027}


def main():
    if os.name != "posix" or not Path("/proc").exists():
        sys.exit("Esta verificación necesita Linux (o WSL): usa /proc, ps y señales POSIX.")
    pedidos = sys.argv[1:] or list(CASOS)
    desconocidos = [x for x in pedidos if x not in CASOS]
    if desconocidos:
        sys.exit(f"Casos desconocidos: {desconocidos}. Disponibles: {list(CASOS)}")
    total_ok = True
    for id_caso in pedidos:
        print(f"== {id_caso} ...", flush=True)
        resultado, carpeta, texto = CASOS[id_caso]().escribir()
        for linea in texto[:-1]:
            print("   " + linea)
        print(f"   {resultado} -> {carpeta.relative_to(RAIZ)}\n")
        total_ok &= resultado == "PASS"
    print("TODOS PASAN" if total_ok else "HAY CASOS EN FAIL")
    sys.exit(0 if total_ok else 1)


if __name__ == "__main__":
    main()
