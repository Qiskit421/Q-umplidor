#!/usr/bin/env bash
# Mecanismo de construcción de Q-umplidor (doc. 04, "Construcción y dependencias").
#
# Uso, desde la raíz del repositorio:
#   ./construir.sh             verificación rápida (unos segundos)
#   ./construir.sh --completo  además corre las pruebas del Avance 01 y las de red
#                              (cierra antes Q-umplidor: usan data/ y el puerto 5000)
#
# Python no genera un ejecutable: "construir" aquí es comprobar, siempre de la
# misma forma, que el código está listo para correr. Termina con código 0 si
# todo pasó y con 1 si algo falló. Detalle: docs/technical-guide/Construccion.md
set -u
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
MINIMO="3.10"
fallas=0

paso() { printf '\n== %s\n' "$1"; }
ok()   { printf '   OK  %s\n' "$1"; }
mal()  { printf '   FALLA  %s\n' "$1"; fallas=$((fallas + 1)); }

paso "1. Python"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    mal "no se encontró $PYTHON (instálalo con: sudo apt install python3)"
    exit 1
fi
version=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if "$PYTHON" -c "import sys; sys.exit(sys.version_info < (${MINIMO/./, }))"; then
    ok "Python $version (se necesita $MINIMO o más nuevo)"
else
    mal "Python $version es muy viejo: se necesita $MINIMO o más nuevo"
    exit 1
fi

paso "2. Dependencias"
# ADR-0001: solo biblioteca estándar. Si algún import no es de la biblioteca
# estándar ni de src/, se marca aquí.
"$PYTHON" - <<'EOF'
import ast, sys
from pathlib import Path
propios = {p.stem for p in Path("src").glob("*.py")}
externos = set()
for archivo in Path("src").glob("*.py"):
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        nombres = []
        if isinstance(nodo, ast.Import):
            nombres = [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0:
            nombres = [nodo.module]
        for nombre in nombres:
            raiz = nombre.split(".")[0]
            if raiz not in propios and raiz not in sys.stdlib_module_names:
                externos.add(f"{raiz} ({archivo})")
if externos:
    print("   FALLA  dependencias externas no declaradas: " + ", ".join(sorted(externos)))
    sys.exit(1)
print("   OK  solo biblioteca estándar de Python (ADR-0001); no hay nada que instalar")
EOF
[ $? -eq 0 ] || fallas=$((fallas + 1))

paso "3. Compilación con advertencias como errores"
# -W error convierte cualquier advertencia del compilador (por ejemplo un
# escape inválido en un texto) en error. Se compila a una carpeta temporal
# para no dejar __pycache__ en el repositorio.
temporal=$(mktemp -d)
if PYTHONPYCACHEPREFIX="$temporal" "$PYTHON" -W error -m compileall -q src verif/scripts verif/test-cases >/dev/null; then
    ok "src/, verif/scripts/ y verif/test-cases/ compilan sin advertencias"
else
    PYTHONPYCACHEPREFIX="$temporal" "$PYTHON" -W error -m compileall -q src verif/scripts verif/test-cases
    mal "hay errores o advertencias de compilación (arriba)"
fi
rm -rf "$temporal"

paso "4. Análisis estático (pyflakes)"
if "$PYTHON" -m pyflakes --version >/dev/null 2>&1; then
    if "$PYTHON" -m pyflakes src verif/scripts verif/test-cases; then
        ok "sin avisos"
    else
        mal "pyflakes encontró avisos (arriba)"
    fi
else
    echo "   OMITIDO  pyflakes no está instalado (opcional: sudo apt install pyflakes3)"
fi

paso "5. Pruebas unitarias"
if "$PYTHON" -m unittest discover -s verif/test-cases -q; then
    ok "bitácora y protocolo"
else
    mal "fallaron pruebas unitarias (arriba)"
fi

if [ "${1:-}" = "--completo" ]; then
    paso "6. Pruebas del Avance 01 (CP-001 a CP-008)"
    if "$PYTHON" verif/scripts/test_avance1_completo.py; then
        ok "Avance 01"
    else
        mal "fallaron pruebas del Avance 01 (arriba)"
    fi
    paso "7. Pruebas de red (TC-028 a TC-037)"
    if "$PYTHON" verif/scripts/prueba_red.py; then
        ok "red"
    else
        mal "fallaron pruebas de red (arriba)"
    fi
fi

echo
if [ "$fallas" -eq 0 ]; then
    echo "CONSTRUCCIÓN: OK"
    exit 0
fi
echo "CONSTRUCCIÓN: FALLA ($fallas paso(s))"
exit 1
