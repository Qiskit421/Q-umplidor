import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import validacion as v


class PruebasValidacionSolicitudes(unittest.TestCase):
    def test_comando_normal_es_valido(self):
        self.assertIsNone(v.validar_solicitud("queue echo hola"))

    def test_solicitud_vacia(self):
        self.assertIn("vacía", v.validar_solicitud(""))

    def test_solo_espacios(self):
        self.assertIn("vacía", v.validar_solicitud("   \t "))

    def test_justo_en_el_limite_es_valida(self):
        self.assertIsNone(v.validar_solicitud("a" * v.LONGITUD_MAXIMA))

    def test_un_caracter_sobre_el_limite_se_rechaza(self):
        self.assertIn("demasiado larga", v.validar_solicitud("a" * (v.LONGITUD_MAXIMA + 1)))

    def test_caracter_nulo_se_rechaza(self):
        self.assertIn("control", v.validar_solicitud("queue echo a\x00b"))

    def test_salto_de_linea_dentro_del_comando_se_rechaza(self):
        self.assertIn("control", v.validar_solicitud("queue echo a\nqueue echo b"))

    def test_tabulador_es_valido(self):
        self.assertIsNone(v.validar_solicitud("queue\techo hola"))


if __name__ == "__main__":
    unittest.main()