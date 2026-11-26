"""Pruebas de mensajes fragmentados y desconexiones del servidor (TC-028 a TC-037).

Uso (desde la raíz del repositorio):
    python3 verif/scripts/prueba_red.py            # todos los casos
    python3 verif/scripts/prueba_red.py TC-033     # uno o varios casos

Copia src/ a una carpeta temporal y arranca ahí src/servidor.py, así no toca
el data/ del repositorio. Necesita el puerto 5000 libre (cierra antes cualquier
servidor de Q-umplidor que tengas abierto). Tarda unos 5 segundos.
Guarda la salida y el entorno en verif/results/TC-028-037-<fecha>/.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PUERTO = 5000
INACTIVIDAD = 3  # segundos; el servidor usa 300 por defecto, aquí se baja para no esperar


class Servidor:
    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="q-umplidor-red-"))
        shutil.copytree(REPO / "src", self.dir / "src")
        self.proc = None
        self.clave = None

    def arrancar(self):
        self.log = self.dir / f"pantalla-{int(time.time() * 1000)}.log"
        # stdin abierto y vacío: la consola del servidor se queda esperando.
        self.proc = subprocess.Popen(
            [sys.executable, "src/servidor.py"], cwd=self.dir,
            stdin=subprocess.PIPE, stdout=open(self.log, "w"), stderr=subprocess.STDOUT,
            env={**os.environ, "Q_INACTIVIDAD": str(INACTIVIDAD)},
        )
        for _ in range(50):
            time.sleep(0.1)
            m = re.search(r"Clave de acceso: (\d+)", self.log.read_text())
            if m:
                self.clave = m.group(1)
                return True
            if self.proc.poll() is not None:
                break
        return False

    def vivo(self):
        return self.proc.poll() is None

    def pantalla(self):
        return "".join(p.read_text() for p in self.dir.glob("pantalla-*.log"))

    def detener(self):
        if self.proc and self.vivo():
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def eventos(self):
        archivo = self.dir / "data" / "events.jsonl"
        if not archivo.exists():
            return []
        return [json.loads(linea) for linea in archivo.read_text().splitlines() if linea.strip()]


def leer_linea(s):
    datos = b""
    while not datos.endswith(b"\n"):
        trozo = s.recv(4096)
        if not trozo:
            break
        datos += trozo
    return datos.decode("utf-8", "replace")


def pedir(s, mensaje):
    s.sendall(mensaje)
    return json.loads(leer_linea(s))


def conectar():
    s = socket.create_connection(("127.0.0.1", PUERTO), timeout=5)
    assert pedir(s, (json.dumps({"clave": SRV.clave}) + "\n").encode()).get("ok"), "clave rechazada"
    return s


LIMITE = b'{"comando": "limite"}\n'


def es_limite(respuesta):
    return "concurrencia" in respuesta.get("salida", "")


# ---------------------------------------------------------------- casos
def tc028():
    """Mensaje normal: un comando, una respuesta."""
    with conectar() as s:
        r = pedir(s, LIMITE)
    return es_limite(r), repr(r.get("salida", ""))[:70]


def tc029():
    """Mensaje fragmentado: el comando llega de 1 byte en 1 byte."""
    with conectar() as s:
        for b in LIMITE:
            s.sendall(bytes([b]))
            time.sleep(0.01)
        r = json.loads(leer_linea(s))
    return es_limite(r), f"{len(LIMITE)} envíos de 1 byte -> una respuesta completa"


def tc030():
    """Dos mensajes pegados en un solo envío."""
    with conectar() as s:
        s.sendall(LIMITE + b'{"comando": "politica"}\n')
        r1 = json.loads(leer_linea(s))
        r2 = json.loads(leer_linea(s))
    return es_limite(r1) and bool(r2.get("salida")), "dos respuestas separadas, en orden"


def tc031():
    """JSON inválido: responde error y la misma conexión sigue sirviendo."""
    with conectar() as s:
        r = pedir(s, b"esto no es json\n")
        sigue = es_limite(pedir(s, LIMITE))
    return "no válida" in r.get("salida", "") and sigue, repr(r.get("salida", ""))[:70]


def tc032():
    """Bytes que no son UTF-8: responde error y la conexión sigue."""
    with conectar() as s:
        r = pedir(s, b'{"comando": "\xff\xfe"}\n')
        sigue = es_limite(pedir(s, LIMITE))
    return "UTF-8" in r.get("salida", "") and sigue, repr(r.get("salida", ""))[:70]


def tc033():
    """Más de 64 KiB sin fin de mensaje: el servidor corta esa conexión y sigue vivo."""
    s = conectar()
    s.settimeout(5)
    enviados, aviso = 0, ""
    try:
        for _ in range(160):  # hasta ~10 MB
            s.sendall(b"A" * 65536)
            enviados += 65536
        cortada = False
    except OSError:
        cortada = True
    try:
        aviso = leer_linea(s).strip()
    except OSError:
        pass
    s.close()
    ok = cortada and SRV.vivo() and es_limite(pedir(conectar(), LIMITE))
    return ok, f"{'cortó' if cortada else 'NO cortó'} la conexión tras {enviados // 1024} KB; aviso={aviso[:50]}"


def tc034():
    """El cliente se va a mitad de un comando: el trabajo queda registrado."""
    s = conectar()
    s.sendall(b'{"comando": "queue sleep 2"}\n')
    s.close()  # no espera la respuesta
    time.sleep(0.5)
    with conectar() as s2:
        r = pedir(s2, b'{"comando": "queue"}\n')
    return "sleep 2" in r.get("salida", "") and SRV.vivo(), "servidor vivo y el trabajo aparece en queue"


def tc035():
    """El cliente se va a mitad de un mensaje: lo incompleto se descarta."""
    s = conectar()
    s.sendall(b'{"comando": "queue sleep 7')  # sin cierre ni fin de mensaje
    s.close()
    time.sleep(0.5)
    with conectar() as s2:
        r = pedir(s2, b'{"comando": "queue"}\n')
    return "sleep 7" not in r.get("salida", "") and SRV.vivo(), "nada se ejecutó del mensaje partido"


def tc036():
    """Cliente conectado que no manda nada: se cierra por inactividad con aviso."""
    s = socket.create_connection(("127.0.0.1", PUERTO), timeout=INACTIVIDAD + 10)
    t0, recibido, cerrada = time.time(), b"", False
    try:
        while True:
            d = s.recv(4096)
            if not d:
                cerrada = True
                break
            recibido += d
    except socket.timeout:
        pass
    s.close()
    t = time.time() - t0
    aviso = recibido.decode("utf-8", "replace")
    ok = cerrada and "inactividad" in aviso and INACTIVIDAD - 1 <= t <= INACTIVIDAD + 3
    return ok, f"cerrada a los {t:.1f} s (Q_INACTIVIDAD={INACTIVIDAD}); aviso={aviso.strip()[:50]}"


def tc037():
    """Se cierra el servidor con un cliente conectado y se vuelve a abrir enseguida."""
    s = conectar()
    SRV.detener()
    try:
        perdida = leer_linea(s) == ""  # el cliente se entera: la conexión se cerró
    except OSError:
        perdida = True
    s.close()
    if not SRV.arrancar():
        return False, "no pudo volver a arrancar: " + SRV.log.read_text().strip().splitlines()[-1][:80]
    with conectar() as s2:
        ok = es_limite(pedir(s2, LIMITE))
    return perdida and ok, "el cliente detectó el cierre y el servidor reabrió el puerto de inmediato"


CASOS = {
    "TC-028": ("Mensaje normal", tc028),
    "TC-029": ("Mensaje fragmentado byte a byte", tc029),
    "TC-030": ("Dos mensajes en un solo envío", tc030),
    "TC-031": ("JSON inválido", tc031),
    "TC-032": ("Mensaje que no es UTF-8", tc032),
    "TC-033": ("Mensaje demasiado grande", tc033),
    "TC-034": ("Desconexión a mitad de un comando", tc034),
    "TC-035": ("Desconexión a mitad de un mensaje", tc035),
    "TC-036": ("Cliente inactivo", tc036),
    "TC-037": ("Reinicio con clientes conectados", tc037),
}


def puerto_ocupado():
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PUERTO)) == 0


class Copia:
    """Escribe en pantalla y además guarda el texto para la evidencia."""

    def __init__(self, pantalla):
        self.pantalla, self.texto = pantalla, []

    def write(self, t):
        self.pantalla.write(t)
        self.texto.append(t)

    def flush(self):
        self.pantalla.flush()


def guardar_evidencia(texto):
    carpeta = REPO / "verif" / "results" / f"TC-028-037-{time.strftime('%Y%m%d')}"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "salida_consola.txt").write_text(texto, encoding="utf-8")
    entorno = [
        f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Python: {sys.version.split()[0]}",
        f"Sistema: {' '.join(os.uname()[i] for i in (0, 2, 4))}",
        f"Commit: {subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip() or '(sin git)'}",
        f"Comando: python3 verif/scripts/prueba_red.py {' '.join(sys.argv[1:])}".rstrip(),
        f"Q_INACTIVIDAD={INACTIVIDAD}",
    ]
    (carpeta / "entorno.txt").write_text("\n".join(entorno) + "\n", encoding="utf-8")
    return carpeta


if __name__ == "__main__":
    sys.stdout = Copia(sys.stdout)
    pedidos = [a.upper() for a in sys.argv[1:]] or list(CASOS)
    desconocidos = [p for p in pedidos if p not in CASOS]
    if desconocidos:
        raise SystemExit(f"Casos desconocidos: {', '.join(desconocidos)}. Disponibles: {', '.join(CASOS)}")
    if puerto_ocupado():
        raise SystemExit(f"El puerto {PUERTO} está ocupado: cierra el servidor de Q-umplidor y vuelve a intentar.")

    SRV = Servidor()
    if not SRV.arrancar():
        raise SystemExit("El servidor no arrancó:\n" + SRV.pantalla())
    print(f"Servidor de prueba en {SRV.dir} (Q_INACTIVIDAD={INACTIVIDAD})\n")

    fallas = 0
    for tc in pedidos:
        nombre, funcion = CASOS[tc]
        try:
            ok, detalle = funcion()
        except Exception as e:
            ok, detalle = False, f"excepción {type(e).__name__}: {e}"
        fallas += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {tc} {nombre}: {detalle}")

    vivo = SRV.vivo()
    SRV.detener()
    pantalla = SRV.pantalla()
    conexiones = [e for e in SRV.eventos() if e.get("event", "").startswith("CLIENT_")]
    print()
    print(f"Servidor vivo al terminar: {'sí' if vivo else 'NO'}")
    print(f"Traceback en la pantalla del servidor: {'SÍ' if 'Traceback' in pantalla else 'no'}")
    print(f"Eventos de conexión en la bitácora: {len(conexiones)}")
    for e in conexiones:
        datos = e.get("details", e)
        if e["event"] == "CLIENT_DISCONNECTED":
            print(f"  {datos.get('cliente')}: {datos.get('motivo')}")
    if "Traceback" in pantalla:
        fallas += 1
        print(pantalla[pantalla.index("Traceback"):][:800])
    if not vivo:
        fallas += 1

    shutil.rmtree(SRV.dir, ignore_errors=True)
    print(f"\nResultado: {'PASS' if not fallas else f'FAIL ({fallas} falla(s))'}")
    carpeta = guardar_evidencia("".join(sys.stdout.texto))
    print(f"Evidencia: {carpeta.relative_to(REPO)}/")
    sys.exit(1 if fallas else 0)
