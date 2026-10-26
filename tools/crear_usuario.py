"""
Crea un usuario desde la terminal (útil si se pierde el acceso del administrador).

Uso:
    python tools/crear_usuario.py --usuario admin2 --rol admin
La clave se pide sin mostrarse en pantalla y debe cumplir la política (10+ caracteres, letras y números).
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from config import Config
    from noc import autenticacion, db
    p = argparse.ArgumentParser(description="Crear usuario del NOC")
    p.add_argument("--usuario", required=True)
    p.add_argument("--nombre", default="")
    p.add_argument("--rol", required=True, choices=Config.ROLES)
    a = p.parse_args()
    clave = getpass.getpass("Clave: ")
    if clave != getpass.getpass("Repite la clave: "):
        sys.exit("Las claves no coinciden.")
    conn = db.connect(Config.DB_PATH)
    db.init_db(conn)
    try:
        uid = autenticacion.crear_usuario(conn, a.usuario, a.nombre, a.rol, clave, "terminal", debe_cambiar=False)
    except autenticacion.ErrorAutenticacion as e:
        sys.exit(f"Error: {e}")
    db.registrar_auditoria(conn, "terminal", "admin", "crear_usuario", f"usuario #{uid}", f"{a.usuario} ({a.rol}) desde la terminal")
    print(f"Usuario {a.usuario} creado con rol {a.rol}.")


if __name__ == "__main__":
    main()
