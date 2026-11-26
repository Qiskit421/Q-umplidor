import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import event_log as ev  # noqa: E402
import salud  # noqa: E402


def reg(evento, seq=1, **detalles):
    return {"seq": seq, "ts": "2026-11-26T06:00:00.000+00:00",
            "event": evento, "job_id": None, "details": detalles}


def resumen(registros=(), **cambios):
    datos = dict(inicio=1000.0, ahora=1000.0, en_ejecucion=0, limite=3, en_cola=0,
                 capacidad=5, en_segundo_plano=0, registros=list(registros))
    datos.update(cambios)
    return "\n".join(salud.construir_resumen(**datos))


class PruebasResumenDeSalud(unittest.TestCase):
    def test_muestra_el_servicio_activo(self):
        self.assertIn("ACTIVO", resumen())

    def test_muestra_trabajos_en_ejecucion_y_en_cola(self):
        texto = resumen(en_ejecucion=2, en_cola=1)
        self.assertIn("2 de 3", texto)
        self.assertIn("1 de 5", texto)

    def test_sin_errores(self):
        self.assertIn("ninguno", resumen())

    def test_rechazos_y_accesos_denegados_son_errores(self):
        texto = resumen([
            reg(ev.JOB_REJECTED, 1, motivo="cola llena"),
            reg(ev.ACCESS_DENIED, 2, ip="10.0.0.5", motivo="IP_NO_PERMITIDA"),
        ])
        self.assertIn("JOB_REJECTED", texto)
        self.assertIn("ACCESS_DENIED", texto)

    def test_trabajo_fallido_es_error_y_terminado_no(self):
        self.assertIn("JOB_FINISHED", resumen([reg(ev.JOB_FINISHED, estado="Falló (código 1)", exit_code=1)]))
        self.assertIn("ninguno", resumen([reg(ev.JOB_FINISHED, estado="Terminado", exit_code=0)]))

    def test_eventos_normales_no_son_errores(self):
        normales = [reg(ev.SYSTEM_STARTED, 1), reg(ev.JOB_SUBMITTED, 2),
                    reg(ev.JOB_STARTED, 3), reg(ev.JOB_CANCELLED, 4, estado="Cancelado")]
        self.assertIn("ninguno", resumen(normales))

    def test_solo_muestra_los_ultimos_errores(self):
        registros = [reg(ev.JOB_REJECTED, i, motivo=f"m{i}") for i in range(1, 9)]
        texto = resumen(registros)
        self.assertIn("últimos 5 de 8", texto)
        self.assertIn("motivo=m8", texto)
        self.assertIn("motivo=m4", texto)
        self.assertNotIn("motivo=m3", texto)

    def test_formato_de_duracion(self):
        self.assertEqual(salud.formatear_duracion(3725), "1h 02m 05s")
        self.assertEqual(salud.formatear_duracion(-5), "0h 00m 00s")

    def test_muestra_la_red_solo_si_existe(self):
        self.assertIn("escuchando en 127.0.0.1:5000", resumen(red="escuchando en 127.0.0.1:5000"))
        self.assertNotIn("Servidor de red", resumen())


if __name__ == "__main__":
    unittest.main()