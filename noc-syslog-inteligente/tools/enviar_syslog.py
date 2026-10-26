"""
Envía mensajes Syslog por UDP al receptor del NOC (prueba del receptor real).

Uso:
    python tools/enviar_syslog.py                      # 5 mensajes de prueba a 127.0.0.1:5514
    python tools/enviar_syslog.py --host 192.168.1.20 --puerto 5514 --archivo samples/syslog_simulado.log

Los paquetes salen desde la IP de este PC. Si se envían a 127.0.0.1 llegan
como el equipo "LAB-LOCALHOST" del inventario (127.0.0.1). Si se envían desde
otro PC, esa IP debe estar registrada en el inventario o los eventos quedarán
marcados como "fuente no autorizada" (así funciona la lista permitida).
"""
import argparse
import socket
import time
from datetime import datetime

PRUEBA = [
    (6, "Mensaje de prueba informativo enviado por UDP"),
    (5, "Interface GigabitEthernet0/1 changed state to up"),
    (4, "Login failed [user: admin] [Source: 198.51.100.77]"),
    (3, "Interface GigabitEthernet0/2 changed state to down"),
    (2, "Temperatura del chasis por encima del umbral"),
]


def main():
    p = argparse.ArgumentParser(description="Envía mensajes Syslog de prueba por UDP")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=5514)
    p.add_argument("--archivo", help="archivo con un mensaje Syslog por línea")
    a = p.parse_args()

    if a.archivo:
        with open(a.archivo, encoding="utf-8") as f:
            mensajes = [l.strip() for l in f if l.strip()]
    else:
        ahora = datetime.now()
        marca = ahora.strftime("%b ") + f"{ahora.day:>2}" + ahora.strftime(" %H:%M:%S")
        mensajes = [f"<{23 * 8 + sev}>{marca} LAB-LOCALHOST prueba[{100 + i}]: {txt}"
                    for i, (sev, txt) in enumerate(PRUEBA)]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for m in mensajes:
            s.sendto(m.encode("utf-8"), (a.host, a.puerto))
            print("enviado:", m[:100])
            time.sleep(0.05)
    print(f"\n{len(mensajes)} mensajes enviados a {a.host}:{a.puerto}/udp")


if __name__ == "__main__":
    main()
