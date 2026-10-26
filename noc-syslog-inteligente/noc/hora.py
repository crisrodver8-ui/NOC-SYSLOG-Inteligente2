"""
Verificación de la hora del SERVIDOR contra un servidor NTP (protocolo SNTP, RFC 4330).

Todas las fechas del sistema las pone el servidor (db.ahora()), por eso es
importante comprobar que su reloj esté sincronizado. Si el desfase supera el
máximo permitido, el panel lo muestra en rojo y queda en la auditoría.
"""
import socket
import struct
import threading
import time
from datetime import datetime

_DIFERENCIA_1900_1970 = 2208988800  # segundos entre la época NTP (1900) y la Unix (1970)

estado = {"verificado": False, "servidor": None, "desfase_ms": None, "sincronizado": None,
          "ultima_verificacion": None, "error": None}
_lock = threading.Lock()


def consultar_ntp(servidor: str, timeout: float = 3.0, puerto: int = 123) -> float:
    """Devuelve el desfase en milisegundos (positivo = el reloj local está atrasado)."""
    paquete = b"\x1b" + 47 * b"\0"  # LI=0, versión 3, modo cliente
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = time.time()
        s.sendto(paquete, (servidor, puerto))
        datos, _ = s.recvfrom(48)
        t4 = time.time()
    if len(datos) < 48:
        raise ValueError("Respuesta NTP incompleta")
    seg_rx, frac_rx, seg_tx, frac_tx = struct.unpack("!12I", datos)[8:12]
    t2 = seg_rx - _DIFERENCIA_1900_1970 + frac_rx / 2**32   # hora en que el servidor recibió
    t3 = seg_tx - _DIFERENCIA_1900_1970 + frac_tx / 2**32   # hora en que el servidor respondió
    return ((t2 - t1) + (t3 - t4)) / 2 * 1000


def verificar(servidor: str, maximo_ms: int) -> dict:
    with _lock:
        try:
            desfase = consultar_ntp(servidor)
            estado.update(verificado=True, servidor=servidor, desfase_ms=round(desfase),
                          sincronizado=abs(desfase) <= maximo_ms, error=None)
        except (OSError, ValueError) as exc:
            estado.update(verificado=False, servidor=servidor, desfase_ms=None, sincronizado=None,
                          error=f"No se pudo consultar NTP ({exc.__class__.__name__}). Revisa la conexión a internet o NTP_SERVIDOR.")
        estado["ultima_verificacion"] = datetime.now().isoformat(timespec="seconds")
        return dict(estado)


def iniciar_verificacion_periodica(servidor: str, maximo_ms: int, cada_s: int = 900):
    """Verifica al arrancar y luego cada 15 minutos, en segundo plano."""
    def bucle():
        while True:
            verificar(servidor, maximo_ms)
            time.sleep(cada_s)
    threading.Thread(target=bucle, daemon=True, name="verificador-ntp").start()
