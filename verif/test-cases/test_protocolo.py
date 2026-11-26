"""Pruebas unitarias de src/protocolo.py (RF-21), sin arrancar el servidor.

Usa socket.socketpair(): dos sockets conectados entre sí dentro del mismo
proceso. Lo que se escribe en uno se lee en el otro, igual que por la red.
Se corren con: python3 -m unittest discover -s verif/test-cases -v
"""
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
import protocolo  # noqa: E402


class TestProtocolo(unittest.TestCase):
    def setUp(self):
        self.escribe, self.lee = socket.socketpair()
        self.lee.settimeout(2)
        self.lector = protocolo.LectorMensajes(self.lee, max_mensaje=64)

    def tearDown(self):
        self.escribe.close()
        self.lee.close()

    def test_ida_y_vuelta(self):
        protocolo.enviar_mensaje(self.escribe, {"comando": "queue sleep 5", "acento": "ñ"})
        self.assertEqual(self.lector.leer(), {"comando": "queue sleep 5", "acento": "ñ"})

    def test_mensaje_partido_en_varios_envios(self):
        for pedazo in (b'{"coma', b'ndo": "li', b'mite"}', b"\n"):
            self.escribe.sendall(pedazo)
        self.assertEqual(self.lector.leer(), {"comando": "limite"})

    def test_caracter_utf8_partido_entre_dos_envios(self):
        texto = '{"c": "ñ"}\n'.encode("utf-8")
        corte = texto.index("ñ".encode("utf-8")) + 1  # a la mitad de los 2 bytes de la ñ
        self.escribe.sendall(texto[:corte])
        self.escribe.sendall(texto[corte:])
        self.assertEqual(self.lector.leer(), {"c": "ñ"})

    def test_dos_mensajes_pegados(self):
        self.escribe.sendall(b'{"a": 1}\n{"b": 2}\n')
        self.assertEqual(self.lector.leer(), {"a": 1})
        self.assertEqual(self.lector.leer(), {"b": 2})

    def test_acepta_fin_de_linea_de_windows(self):
        self.escribe.sendall(b'{"a": 1}\r\n')
        self.assertEqual(self.lector.leer(), {"a": 1})

    def test_json_invalido_no_rompe_el_siguiente(self):
        self.escribe.sendall(b'no es json\n{"a": 1}\n')
        with self.assertRaises(protocolo.MensajeInvalido):
            self.lector.leer()
        self.assertEqual(self.lector.leer(), {"a": 1})

    def test_utf8_invalido(self):
        self.escribe.sendall(b'{"a": "\xff"}\n')
        with self.assertRaisesRegex(protocolo.MensajeInvalido, "UTF-8"):
            self.lector.leer()

    def test_debe_ser_objeto(self):
        self.escribe.sendall(b"[1, 2]\n")
        with self.assertRaisesRegex(protocolo.MensajeInvalido, "objeto"):
            self.lector.leer()

    def test_demasiado_grande_sin_fin(self):
        self.escribe.sendall(b"A" * 100)
        with self.assertRaises(protocolo.MensajeDemasiadoGrande):
            self.lector.leer()

    def test_demasiado_grande_con_fin(self):
        self.escribe.sendall(b'{"a": "' + b"x" * 80 + b'"}\n')
        with self.assertRaises(protocolo.MensajeDemasiadoGrande):
            self.lector.leer()

    def test_cierre_limpio(self):
        self.escribe.close()
        with self.assertRaises(protocolo.ConexionCerrada) as caso:
            self.lector.leer()
        self.assertEqual(caso.exception.incompletos, 0)

    def test_cierre_a_mitad_de_mensaje(self):
        self.escribe.sendall(b'{"comando": "que')
        self.escribe.close()
        with self.assertRaises(protocolo.ConexionCerrada) as caso:
            self.lector.leer()
        self.assertEqual(caso.exception.incompletos, len(b'{"comando": "que'))


if __name__ == "__main__":
    unittest.main()
