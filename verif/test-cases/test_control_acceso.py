import ipaddress
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import control_acceso as ac


class PruebasAccesoPorRed(unittest.TestCase):
    def setUp(self):
        self.politica = ac.AccessPolicy(
            [ipaddress.ip_network("127.0.0.1/32"), ipaddress.ip_network("192.168.1.0/24")]
        )

    def test_ip_dentro_de_red_permitida(self):
        self.assertTrue(self.politica.is_allowed("192.168.1.50"))

    def test_ip_fuera_de_la_lista(self):
        self.assertFalse(self.politica.is_allowed("192.168.2.50"))

    def test_ip_malformada(self):
        self.assertFalse(self.politica.is_allowed("no-es-una-ip"))

    def test_ipv4_mapeada_en_ipv6(self):
        self.assertTrue(self.politica.is_allowed("::ffff:127.0.0.1"))

    def test_config_rechaza_red_publica(self):
        os.environ["Q_REDES_PERMITIDAS"] = "8.8.8.0/24"
        try:
            with self.assertRaises(SystemExit):
                ac.leer_redes_permitidas()
        finally:
            del os.environ["Q_REDES_PERMITIDAS"]

    def test_config_por_defecto_solo_localhost(self):
        os.environ.pop("Q_REDES_PERMITIDAS", None)
        redes = [str(r) for r in ac.leer_redes_permitidas()]
        self.assertEqual(redes, ["127.0.0.1/32", "::1/128"])


if __name__ == "__main__":
    unittest.main()
