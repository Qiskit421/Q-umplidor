import ipaddress
import os


def leer_redes_permitidas():
    """Q_REDES_PERMITIDAS="192.168.1.0/24,127.0.0.1/32"; por defecto solo localhost (RNF-12)."""
    texto = os.environ.get("Q_REDES_PERMITIDAS", "127.0.0.1/32,::1/128")
    redes = []
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            red = ipaddress.ip_network(parte, strict=False)
        except ValueError:
            raise SystemExit(f"Q_REDES_PERMITIDAS: '{parte}' no es una red válida (ejemplo: 192.168.1.0/24)")
        if not (red.is_private or red.is_loopback):
            raise SystemExit(f"Q_REDES_PERMITIDAS: '{parte}' no es una red privada ni localhost (RNF-13)")
        redes.append(red)
    if not redes:
        raise SystemExit("Q_REDES_PERMITIDAS no puede estar vacía")
    return redes


class AccessPolicy:
    def __init__(self, redes):
        self._redes = list(redes)

    def is_allowed(self, ip_str):
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        return any(ip in red for red in self._redes)