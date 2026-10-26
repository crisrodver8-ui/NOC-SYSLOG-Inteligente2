"""
RESPALDO de la base de datos (en caliente, sin detener la aplicación).

Uso:
    python tools/respaldo.py                 # crea respaldos/noc-AAAAMMDD-HHMMSS.db + .sha256
    python tools/respaldo.py --conservar 14  # además borra los respaldos más antiguos (deja 14)

- Usa la API de respaldo de SQLite (copia consistente aunque el receptor esté escribiendo).
- Verifica la copia con PRAGMA integrity_check y la cadena de la auditoría.
- Guarda la huella SHA-256 para detectar si el respaldo se altera después.
"""
import argparse
import glob
import hashlib
import os
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)


def sha256(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def crear_respaldo(db_path: str, carpeta: str) -> dict:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"No existe la base de datos {db_path}")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, f"noc-{datetime.now():%Y%m%d-%H%M%S}.db")
    origen = sqlite3.connect(db_path)
    copia = sqlite3.connect(destino)
    with copia:
        origen.backup(copia)            # copia consistente en caliente
    origen.close()
    copia.row_factory = sqlite3.Row
    integridad = copia.execute("PRAGMA integrity_check").fetchone()[0]
    from noc.db import verificar_cadena
    cadena = verificar_cadena(copia)
    conteos = {t: copia.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
               for t in ("dispositivos", "eventos", "incidentes", "acciones", "auditoria", "usuarios")}
    copia.close()
    huella = sha256(destino)
    with open(destino + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{huella}  {os.path.basename(destino)}\n")
    if integridad != "ok" or not cadena["integra"]:
        raise RuntimeError(f"El respaldo NO es válido: integridad={integridad}, auditoría íntegra={cadena['integra']}")
    return {"archivo": destino, "sha256": huella, "conteos": conteos, "tamano_kb": round(os.path.getsize(destino) / 1024, 1)}


def rotar(carpeta: str, conservar: int) -> list[str]:
    archivos = sorted(glob.glob(os.path.join(carpeta, "noc-*.db")))
    borrados = archivos[:-conservar] if conservar and len(archivos) > conservar else []
    for a in borrados:
        os.remove(a)
        if os.path.exists(a + ".sha256"):
            os.remove(a + ".sha256")
    return borrados


def main():
    from config import Config
    p = argparse.ArgumentParser(description="Respaldo de la base de datos del NOC")
    p.add_argument("--db", default=Config.DB_PATH)
    p.add_argument("--destino", default=Config.RESPALDOS_DIR)
    p.add_argument("--conservar", type=int, default=0, help="cantidad de respaldos a conservar (0 = todos)")
    a = p.parse_args()
    r = crear_respaldo(a.db, a.destino)
    print(f"Respaldo creado: {r['archivo']} ({r['tamano_kb']} KB)")
    print(f"SHA-256: {r['sha256']}")
    print("Registros:", ", ".join(f"{k}={v}" for k, v in r["conteos"].items()))
    print("Verificación: integridad OK, auditoría encadenada OK")
    for b in rotar(a.destino, a.conservar):
        print("Rotado (eliminado):", b)


if __name__ == "__main__":
    main()
