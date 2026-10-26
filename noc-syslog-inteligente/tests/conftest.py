"""
Configuración compartida de las pruebas: cada prueba usa una base de datos temporal nueva
con un usuario por rol. Las pruebas se autentican con tokens de la API (Bearer).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USUARIOS_PRUEBA = {
    "admin": "admin", "supervisor1": "supervisor", "supervisor2": "supervisor",
    "operador1": "operador", "operador2": "operador", "auditor1": "auditor",
}
CLAVE_PRUEBA = "ClaveDePrueba2026"
TOKENS: dict[str, str] = {}


@pytest.fixture
def app(tmp_path):
    from app import create_app  # import aquí: las pruebas del parser no necesitan la app web
    from noc import autenticacion, db
    aplicacion = create_app({"DB_PATH": str(tmp_path / "prueba.db"), "RESPALDOS_DIR": str(tmp_path / "respaldos"),
                             "TESTING": True})
    conn = db.connect(aplicacion.config["DB_PATH"])
    for usuario, rol in USUARIOS_PRUEBA.items():
        uid = autenticacion.crear_usuario(conn, usuario, usuario.title(), rol, CLAVE_PRUEBA, "pruebas", debe_cambiar=False)
        TOKENS[usuario] = autenticacion.crear_token(conn, uid, "pruebas", 1)
    conn.close()
    return aplicacion


@pytest.fixture
def cliente(app):
    return app.test_client()


def cab(usuario="operador1"):
    return {"Authorization": f"Bearer {TOKENS[usuario]}"}
