import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import configuracion  # noqa: E402


class PruebasDirectorioDeDatos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_variable_usa_el_predeterminado(self):
        ruta = configuracion.leer_directorio_datos(self.base / "data", entorno={})
        self.assertEqual(ruta, (self.base / "data").resolve())

    def test_la_variable_cambia_el_directorio(self):
        otra = self.base / "otra"
        ruta = configuracion.leer_directorio_datos(
            self.base / "data", entorno={"Q_DIRECTORIO_DATOS": str(otra)})
        self.assertEqual(ruta, otra.resolve())

    def test_crea_el_directorio_si_no_existe(self):
        nueva = self.base / "a" / "b"
        configuracion.leer_directorio_datos(self.base / "data", entorno={"Q_DIRECTORIO_DATOS": str(nueva)})
        self.assertTrue(nueva.is_dir())

    def test_variable_vacia_usa_el_predeterminado(self):
        ruta = configuracion.leer_directorio_datos(
            self.base / "data", entorno={"Q_DIRECTORIO_DATOS": "   "})
        self.assertEqual(ruta, (self.base / "data").resolve())

    def test_un_archivo_no_sirve_como_directorio(self):
        archivo = self.base / "archivo.txt"
        archivo.write_text("x")
        with self.assertRaises(SystemExit):
            configuracion.leer_directorio_datos(
                self.base / "data", entorno={"Q_DIRECTORIO_DATOS": str(archivo)})

    def test_no_deja_archivos_de_prueba(self):
        ruta = configuracion.leer_directorio_datos(self.base / "data", entorno={})
        self.assertEqual(list(ruta.iterdir()), [])


if __name__ == "__main__":
    unittest.main()