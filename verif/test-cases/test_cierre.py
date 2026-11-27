import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import cierre  # noqa: E402


class PruebasCierreControlado(unittest.TestCase):
    def test_queue_con_comando_crea_un_trabajo(self):
        self.assertTrue(cierre.es_envio_de_trabajo(["queue", "echo", "hola"]))

    def test_sleep_en_segundo_plano_crea_un_trabajo(self):
        self.assertTrue(cierre.es_envio_de_trabajo(["sleep", "10", "&"]))

    def test_ejecutar_crea_un_trabajo(self):
        self.assertTrue(cierre.es_envio_de_trabajo(["ejecutar", "notepad", "&"]))

    def test_sleep_en_primer_plano_no_crea_un_trabajo(self):
        self.assertFalse(cierre.es_envio_de_trabajo(["sleep", "5"]))

    def test_consultas_no_crean_trabajos(self):
        for partes in (["help"], ["listar"], ["estado", "1"], ["salud"], ["eventos"],
                       ["recursos"], ["limite"], ["queue"], ["salida", "1"]):
            self.assertFalse(cierre.es_envio_de_trabajo(partes), partes)

    def test_limpiar_y_cancelar_siguen_permitidos(self):
        self.assertFalse(cierre.es_envio_de_trabajo(["queue", "clear"]))
        self.assertFalse(cierre.es_envio_de_trabajo(["queue", "cancelar", "1"]))
        self.assertFalse(cierre.es_envio_de_trabajo(["cancelar", "1"]))

    def test_solicitud_vacia(self):
        self.assertFalse(cierre.es_envio_de_trabajo([]))


if __name__ == "__main__":
    unittest.main()