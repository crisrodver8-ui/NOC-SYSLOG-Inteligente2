"""
PRUEBA DE CARGA BÁSICA del receptor Syslog (con la aplicación encendida).

Envía N mensajes UDP a una tasa dada desde varias "fuentes" y luego consulta la
API para medir cuántos se procesaron, cuántos se agruparon (duplicados) y cuántos
descartó el control de tormentas.

Uso:
    python tools/prueba_carga.py --token noc_xxx --mensajes 2000 --tasa 200
      --token     token de la API (créalo en la vista «API» con rol operador o superior)
      --mensajes  total de mensajes a enviar
      --tasa      mensajes por segundo

Nota: todos los paquetes salen de este PC (127.0.0.1 = LAB-LOCALHOST), así que con
tasas mayores a LIMITE_MENSAJES_MIN por minuto el control de tormentas descarta el
excedente. Eso es lo esperado y es parte de la prueba.
"""
import argparse
import json
import random
import socket
import time
import urllib.request
from datetime import datetime


def politica(url, token):
    req = urllib.request.Request(url + "/api/politica", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)["contadores"]


def main():
    p = argparse.ArgumentParser(description="Prueba de carga del receptor Syslog")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--puerto", type=int, default=5514)
    p.add_argument("--url", default="http://127.0.0.1:8080")
    p.add_argument("--token", required=True)
    p.add_argument("--mensajes", type=int, default=1000)
    p.add_argument("--tasa", type=int, default=100)
    a = p.parse_args()

    antes = politica(a.url, a.token)
    pausa = 1 / max(a.tasa, 1)
    inicio = time.perf_counter()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for i in range(a.mensajes):
            sev = random.choice([3, 4, 5, 5, 6, 6, 6])
            t = datetime.now()
            msg = (f"<{23 * 8 + sev}>{t:%b} {t.day:>2} {t:%H:%M:%S} LAB-LOCALHOST carga[{i % 50}]: "
                   f"Mensaje de carga {i} interfaz Gi0/{i % 24}")
            s.sendto(msg.encode(), (a.host, a.puerto))
            espera = inicio + (i + 1) * pausa - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
    envio_s = time.perf_counter() - inicio
    time.sleep(3)  # tiempo para que el receptor termine
    despues = politica(a.url, a.token)
    d = {k: despues[k] - antes[k] for k in antes}
    procesados = d["almacenados"] + d["duplicados"] + d["descartados"]
    print("\n=== Resultado de la prueba de carga ===")
    print(f"Enviados:              {a.mensajes} en {envio_s:.1f} s ({a.mensajes / envio_s:.0f} msg/s)")
    print(f"Recibidos por el NOC:  {d['recibidos']}  ({d['recibidos'] / a.mensajes:.1%})")
    print(f"  almacenados nuevos:  {d['almacenados']}")
    print(f"  agrupados (dedup):   {d['duplicados']}")
    print(f"  descartados (tormenta): {d['descartados']}")
    print(f"Pérdida UDP:           {a.mensajes - d['recibidos']}")
    print("Criterio de aceptación: Recibidos ≥ 99 % y la interfaz sigue respondiendo.")
    print("APROBADA" if d["recibidos"] >= 0.99 * a.mensajes and procesados == d["recibidos"] else "REVISAR")


if __name__ == "__main__":
    main()
