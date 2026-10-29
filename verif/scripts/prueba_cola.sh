#!/usr/bin/env bash
# Pruebas TC-005 (cancelar en cola y en ejecución, RF-10) y
# TC-016 (rechazo explícito con cola llena, RF-25 / RNF-29).
# Uso, desde la raíz del repositorio:  bash verif/scripts/prueba_cola.sh
# Borra data/ (historial local de pruebas) antes de cada caso.
set -u
cd "$(dirname "$0")/../.."
FECHA=$(date +%Y%m%d)
COMMIT=$(git rev-parse --short HEAD)
ENTORNO="$(uname -sr), $(python3 --version 2>&1)"

encabezado() {  # $1 = caso, $2 = requisitos, $3 = carpeta
    {
        echo "Caso: $1 ($2)"
        echo "Fecha: $(date)"
        echo "Commit: $COMMIT"
        echo "Entorno: $ENTORNO"
    } > "$3/entorno.txt"
}

# ---------- TC-005: cancelar en cola y en ejecución ----------
R=verif/results/TC-005-$FECHA; mkdir -p "$R"; encabezado TC-005 "RF-10" "$R"
rm -rf data
{
    printf 'queue sleep 2\nqueue sleep 2\nqueue sleep 2\n'
    sleep 0.5
    printf 'cancelar 2\nestado 2\ncancelar 1\n'
    sleep 3
    printf 'listar\n'
} | python3 src/main.py > "$R/salida_consola.txt" 2>&1
INICIO_2=$(python3 -I -c 'import json; d=json.load(open("data/trabajos.json")); print([t for t in d["trabajos"] if t["id"]==2][0]["inicio"])')
echo "inicio del trabajo 2 en trabajos.json: $INICIO_2" >> "$R/salida_consola.txt"
if grep -q 'Trabajo \[2\] cancelado (estaba en cola' "$R/salida_consola.txt" \
   && grep -q '\[2\] sleep 2 -> Cancelado' "$R/salida_consola.txt" \
   && grep -q 'Trabajo \[1\] cancelado' "$R/salida_consola.txt" \
   && grep -qE '^3 +Terminado' "$R/salida_consola.txt" \
   && [ "$INICIO_2" = "None" ]; then
    echo "Resultado: PASS" >> "$R/entorno.txt"
else
    echo "Resultado: FAIL" >> "$R/entorno.txt"
fi

# ---------- TC-016: cola llena con capacidad 2 ----------
R=verif/results/TC-016-$FECHA; mkdir -p "$R"; encabezado TC-016 "RF-25, RNF-29" "$R"
echo "Configuración: Q_CAPACIDAD_COLA=2" >> "$R/entorno.txt"
rm -rf data
{
    printf 'queue sleep 3\n'
    sleep 0.5
    printf 'queue sleep 1\nqueue sleep 1\nqueue sleep 1\n'
    sleep 5
    printf 'queue echo ya hay lugar\n'
    sleep 1
    printf 'listar\n'
} | Q_CAPACIDAD_COLA=2 python3 src/main.py > "$R/salida_consola.txt" 2>&1
if grep -q 'cola llena (2/2 en espera), trabajo rechazado' "$R/salida_consola.txt" \
   && grep -q 'ID: \[4\] agregado a la cola' "$R/salida_consola.txt" \
   && ! grep -q 'ID: \[5\]' "$R/salida_consola.txt"; then
    echo "Resultado: PASS" >> "$R/entorno.txt"
else
    echo "Resultado: FAIL" >> "$R/entorno.txt"
fi

rm -rf data
for c in verif/results/TC-005-"$FECHA" verif/results/TC-016-"$FECHA"; do
    echo "== $c"; cat "$c/entorno.txt"; echo
done
