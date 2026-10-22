"""Configuración compartida de las pruebas: cada prueba usa una base de datos temporal nueva."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app(tmp_path):
    from app import create_app  # import aquí: las pruebas del parser no necesitan la app web
    return create_app({"DB_PATH": str(tmp_path / "prueba.db"), "TESTING": True})


@pytest.fixture
def cliente(app):
    return app.test_client()


def cab(usuario="operador1"):
    return {"X-Usuario": usuario}
