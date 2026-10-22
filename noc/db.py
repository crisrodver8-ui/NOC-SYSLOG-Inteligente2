"""
Acceso a la base de datos SQLite.

- connect(): abre una conexión nueva (la usan las peticiones web y el receptor UDP).
- get_db(): devuelve la conexión de la petición web actual (una por petición).
- init_db(): crea las tablas a partir de schema.sql.
- sembrar_si_vacia(): carga equipos SIMULADOS para poder probar desde cero.
"""
import os
import sqlite3
from datetime import datetime

from flask import current_app, g

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def ahora() -> str:
    """Fecha y hora local en formato ISO (YYYY-MM-DDTHH:MM:SS)."""
    return datetime.now().isoformat(timespec="seconds")


def connect(ruta: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    conn = sqlite3.connect(ruta, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row            # filas accesibles por nombre de columna
    conn.execute("PRAGMA foreign_keys = ON")  # respeta las llaves foráneas
    conn.execute("PRAGMA journal_mode = WAL") # permite leer mientras el receptor escribe
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(conn: sqlite3.Connection):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def filas(cursor) -> list[dict]:
    """Convierte el resultado de una consulta en una lista de diccionarios (para JSON)."""
    return [dict(r) for r in cursor.fetchall()]


# Equipos de laboratorio SIMULADOS. Las IP pertenecen a los rangos de documentación
# del RFC 5737 (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24): no son redes reales.
EQUIPOS_SEMILLA = [
    ("LAB-RT-BORDE01", "198.51.100.1", "Cisco", "ISR 4331", "IOS-XE 17.9.4", "Sede principal - Rack A"),
    ("LAB-FW-PERIM01", "198.51.100.2", "Fortinet", "FortiGate 60F", "FortiOS 7.4.3", "Sede principal - Rack A"),
    ("LAB-SW-DIST01", "198.51.100.10", "Huawei", "S5735-L24T4S", "VRP V200R022", "Sede principal - Rack B"),
    ("LAB-SW-ACC03", "198.51.100.23", "Cisco", "Catalyst 9200L", "IOS-XE 17.6.5", "Bloque 3 - Piso 2"),
    ("LAB-RT-SEDE02", "203.0.113.5", "Huawei", "AR6120", "VRP V300R021", "Sede norte"),
    ("LAB-LOCALHOST", "127.0.0.1", "Otro", "Equipo de pruebas", "-", "PC del estudiante"),
]


def sembrar_si_vacia(conn: sqlite3.Connection):
    if conn.execute("SELECT COUNT(*) FROM dispositivos").fetchone()[0] > 0:
        return
    for nombre, ip, marca, modelo, version, ubicacion in EQUIPOS_SEMILLA:
        conn.execute(
            """INSERT INTO dispositivos (nombre, ip, marca, modelo, version, ubicacion,
                                         estado, autorizado, simulado, actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, 'activo', 1, 1, ?)""",
            (nombre, ip, marca, modelo, version, ubicacion, ahora()),
        )
    conn.commit()


def registrar_auditoria(conn, usuario: str, rol: str, accion: str, objeto: str = "", detalle: str = ""):
    """Escribe una fila en la auditoría. Se llama en cada acción relevante."""
    conn.execute(
        "INSERT INTO auditoria (fecha, usuario, rol, accion, objeto, detalle) VALUES (?, ?, ?, ?, ?, ?)",
        (ahora(), usuario, rol, accion, objeto, detalle[:1000]),
    )
