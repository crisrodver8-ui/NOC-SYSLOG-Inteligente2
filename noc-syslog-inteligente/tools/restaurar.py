"""
RECUPERACIÓN: restaura la base de datos desde un respaldo.

Uso (con la aplicación DETENIDA):
    python tools/restaurar.py --listar
    python tools/restaurar.py respaldos/noc-20261026-180000.db

Pasos que hace:
  1. Verifica la huella SHA-256 del respaldo (que no haya sido alterado).
  2. Verifica PRAGMA integrity_check y la cadena de la auditoría del respaldo.
  3. Guarda la BD actual como data/noc.db.antes-de-restaurar-<fecha> (por si hay que deshacer).
  4. Copia el respaldo en su lugar.
"""
import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from tools.respaldo import sha256  # noqa: E402


def verificar(respaldo: str) -> dict:
    if not os.path.exists(respaldo):
        raise FileNotFoundError(respaldo)
    archivo_huella = respaldo + ".sha256"
    if not os.path.exists(archivo_huella):
        raise RuntimeError("Falta el archivo .sha256 del respaldo: no se puede comprobar que esté intacto.")
    esperado = open(archivo_huella, encoding="utf-8").read().split()[0]
    if sha256(respaldo) != esperado:
        raise RuntimeError("¡La huella SHA-256 no coincide! El respaldo fue modificado o está dañado.")
    conn = sqlite3.connect(respaldo)
    conn.row_factory = sqlite3.Row
    integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
    from noc.db import verificar_cadena
    cadena = verificar_cadena(conn)
    eventos = conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
    conn.close()
    if integridad != "ok" or not cadena["integra"]:
        raise RuntimeError(f"Respaldo inválido (integridad={integridad}, auditoría íntegra={cadena['integra']}).")
    return {"eventos": eventos, "auditoria": cadena["total"]}


def restaurar(respaldo: str, db_path: str) -> str:
    verificar(respaldo)
    previo = ""
    if os.path.exists(db_path):
        previo = f"{db_path}.antes-de-restaurar-{datetime.now():%Y%m%d-%H%M%S}"
        shutil.copy2(db_path, previo)
        for extra in ("-wal", "-shm"):
            if os.path.exists(db_path + extra):
                os.remove(db_path + extra)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    shutil.copy2(respaldo, db_path)
    return previo


def main():
    from config import Config
    p = argparse.ArgumentParser(description="Restaurar la BD del NOC desde un respaldo")
    p.add_argument("respaldo", nargs="?")
    p.add_argument("--db", default=Config.DB_PATH)
    p.add_argument("--listar", action="store_true")
    a = p.parse_args()
    if a.listar or not a.respaldo:
        for r in sorted(glob.glob(os.path.join(Config.RESPALDOS_DIR, "noc-*.db"))):
            print(f"  {r}   ({os.path.getsize(r) // 1024} KB)")
        return
    info = verificar(a.respaldo)
    print(f"Respaldo verificado: {info['eventos']} eventos, {info['auditoria']} registros de auditoría íntegros.")
    if input("¿La aplicación está DETENIDA y deseas restaurar? (si/no): ").strip().lower() != "si":
        print("Cancelado.")
        return
    previo = restaurar(a.respaldo, a.db)
    print("Restauración completada.")
    if previo:
        print(f"La base anterior quedó guardada en: {previo}")


if __name__ == "__main__":
    main()
