"""
Acceso a la base de datos SQLite.

- connect(): abre una conexión nueva (peticiones web, receptor UDP, herramientas).
- get_db(): conexión de la petición web actual.
- init_db(): crea tablas, MIGRA una BD de v0.2.0 y activa las reglas de inmutabilidad.
- registrar_auditoria(): agrega una fila encadenada por hash a la auditoría.
- verificar_cadena(): comprueba que nadie alteró la auditoría.
"""
import hashlib
import os
import sqlite3
import threading
from datetime import datetime

from flask import current_app, g

CARPETA = os.path.dirname(__file__)
VERSION_ESQUEMA = "1.0.0"
_lock_auditoria = threading.Lock()   # la web y el receptor UDP escriben auditoría a la vez


def ahora() -> str:
    """
    Fecha y hora del SERVIDOR en formato ISO (YYYY-MM-DDTHH:MM:SS).
    Es la única fuente de fechas: ningún formulario ni API acepta fechas del usuario.
    """
    return datetime.now().isoformat(timespec="seconds")


def connect(ruta: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    conn = sqlite3.connect(ruta, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def filas(cursor) -> list[dict]:
    return [dict(r) for r in cursor.fetchall()]


def _ejecutar_archivo(conn, nombre):
    with open(os.path.join(CARPETA, nombre), encoding="utf-8") as f:
        conn.executescript(f.read())


# Columnas agregadas en v1.0.0 a tablas que ya existían en v0.2.0
_COLUMNAS_NUEVAS = {
    "dispositivos": [
        ("gestion", "TEXT NOT NULL DEFAULT 'ninguna'"),
        ("ssh_puerto", "INTEGER NOT NULL DEFAULT 22"),
        ("consola_tipo", "TEXT NOT NULL DEFAULT 'ninguna'"),
        ("consola_destino", "TEXT NOT NULL DEFAULT ''"),
        ("consola_velocidad", "INTEGER NOT NULL DEFAULT 9600"),
    ],
    "eventos": [("riesgo", "INTEGER NOT NULL DEFAULT 0"), ("desfase_s", "INTEGER")],
    "auditoria": [("hash_anterior", "TEXT"), ("hash", "TEXT")],
}


def _migrar(conn):
    """Agrega columnas faltantes (BD creada con v0.2.0) y encadena la auditoría antigua."""
    for tabla, columnas in _COLUMNAS_NUEVAS.items():
        existentes = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabla})")}
        for nombre, definicion in columnas:
            if nombre not in existentes:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")
    # Filas de auditoría de v0.2.0 sin hash: se encadenan ANTES de activar los triggers
    if conn.execute("SELECT 1 FROM auditoria WHERE hash IS NULL LIMIT 1").fetchone():
        conn.execute("DROP TRIGGER IF EXISTS auditoria_sin_update")
        anterior = None
        for r in conn.execute("SELECT * FROM auditoria ORDER BY id").fetchall():
            h = r["hash"] or _hash_fila(anterior, r["fecha"], r["usuario"], r["rol"], r["accion"], r["objeto"], r["detalle"])
            if r["hash"] is None:
                conn.execute("UPDATE auditoria SET hash_anterior = ?, hash = ? WHERE id = ?", (anterior, h, r["id"]))
            anterior = h
    conn.commit()


def init_db(conn: sqlite3.Connection):
    _ejecutar_archivo(conn, "schema.sql")
    _migrar(conn)
    _ejecutar_archivo(conn, "schema_triggers.sql")
    if not conn.execute("SELECT 1 FROM esquema_version WHERE version = ?", (VERSION_ESQUEMA,)).fetchone():
        conn.execute("INSERT INTO esquema_version (version, aplicada_en) VALUES (?, ?)", (VERSION_ESQUEMA, ahora()))
    conn.commit()


# ---------------------------------------------------------------- semilla
# Equipos de laboratorio SIMULADOS (IP de documentación RFC 5737).
# consola: (tipo, destino) -> serial = cable de consola por puerto COM; telnet = consola de GNS3
EQUIPOS_SEMILLA = [
    ("LAB-RT-BORDE01", "198.51.100.1", "Cisco", "ISR 4331", "IOS-XE 17.9.4", "Sede principal - Rack A", ("serial", "COM3")),
    ("LAB-FW-PERIM01", "198.51.100.2", "Fortinet", "FortiGate 60F", "FortiOS 7.4.3", "Sede principal - Rack A", ("serial", "COM4")),
    ("LAB-SW-DIST01", "198.51.100.10", "Huawei", "S5735-L24T4S", "VRP V200R022", "Sede principal - Rack B", ("telnet", "127.0.0.1:5002")),
    ("LAB-SW-ACC03", "198.51.100.23", "Cisco", "Catalyst 9200L", "IOS-XE 17.6.5", "Bloque 3 - Piso 2", ("telnet", "127.0.0.1:5003")),
    ("LAB-RT-SEDE02", "203.0.113.5", "Huawei", "AR6120", "VRP V300R021", "Sede norte", ("telnet", "127.0.0.1:5004")),
    ("LAB-LOCALHOST", "127.0.0.1", "Otro", "Equipo de pruebas", "-", "PC del estudiante", ("ninguna", "")),
]


def _puertos_modelo(modelo: str) -> list[tuple]:
    """Puertos físicos típicos de cada modelo: (nombre, tipo, velocidad)."""
    if modelo == "ISR 4331":
        return [("GigabitEthernet0/0/0", "cobre", "1G"), ("GigabitEthernet0/0/1", "cobre", "1G"),
                ("GigabitEthernet0/0/2", "fibra", "1G"), ("GigabitEthernet0", "gestion", "1G"),
                ("Console", "consola", "9600")]
    if modelo == "FortiGate 60F":
        return [("wan1", "cobre", "1G"), ("wan2", "cobre", "1G"), ("dmz", "cobre", "1G")] + \
               [(f"internal{i}", "cobre", "1G") for i in range(1, 6)] + [("Console", "consola", "9600")]
    if modelo == "S5735-L24T4S":
        return [(f"GigabitEthernet0/0/{i}", "cobre", "1G") for i in range(1, 25)] + \
               [(f"XGigabitEthernet0/0/{i}", "fibra", "10G") for i in range(1, 5)] + [("Console", "consola", "9600")]
    if modelo == "Catalyst 9200L":
        return [(f"GigabitEthernet1/0/{i}", "cobre", "1G") for i in range(1, 25)] + \
               [(f"TenGigabitEthernet1/1/{i}", "fibra", "10G") for i in range(1, 5)] + \
               [("GigabitEthernet0/0", "gestion", "1G"), ("Console", "consola", "9600")]
    if modelo == "AR6120":
        return [(f"GigabitEthernet0/0/{i}", "cobre", "1G") for i in range(0, 4)] + \
               [("GigabitEthernet0/0/4", "fibra", "1G"), ("Console", "consola", "9600")]
    return []


def sembrar_si_vacia(conn: sqlite3.Connection):
    from .interfaces import normalizar  # import local para evitar ciclos
    if conn.execute("SELECT COUNT(*) FROM dispositivos").fetchone()[0] > 0:
        return
    for nombre, ip, marca, modelo, version, ubicacion, (ctipo, cdest) in EQUIPOS_SEMILLA:
        cur = conn.execute(
            """INSERT INTO dispositivos (nombre, ip, marca, modelo, version, ubicacion, estado, autorizado,
                   simulado, gestion, consola_tipo, consola_destino, actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, 'activo', 1, 1, 'ninguna', ?, ?, ?)""",
            (nombre, ip, marca, modelo, version, ubicacion, ctipo, cdest, ahora()))
        for i, (pnombre, ptipo, vel) in enumerate(_puertos_modelo(modelo)):
            estado = "up" if ptipo in ("consola", "gestion") or i < 3 else ("down" if i % 4 else "admin_down")
            conn.execute(
                """INSERT INTO interfaces (dispositivo_id, nombre, nombre_norm, tipo, velocidad, estado,
                       origen, actualizado_en) VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)""",
                (cur.lastrowid, pnombre, normalizar(pnombre), ptipo, vel, estado, ahora()))
    conn.commit()


# --------------------------------------------------------------- auditoría
def _hash_fila(anterior, fecha, usuario, rol, accion, objeto, detalle) -> str:
    base = "|".join(str(x) for x in (anterior or "INICIO", fecha, usuario, rol, accion, objeto, detalle))
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def registrar_auditoria(conn, usuario: str, rol: str, accion: str, objeto: str = "", detalle: str = ""):
    """
    Agrega una fila a la auditoría encadenada: hash = SHA-256(hash_anterior + datos).
    La fecha la pone el servidor; nadie puede indicarla.
    """
    detalle = detalle[:1000]
    with _lock_auditoria:
        fila = conn.execute("SELECT hash FROM auditoria ORDER BY id DESC LIMIT 1").fetchone()
        anterior = fila["hash"] if fila else None
        fecha = ahora()
        h = _hash_fila(anterior, fecha, usuario, rol, accion, objeto, detalle)
        conn.execute(
            """INSERT INTO auditoria (fecha, usuario, rol, accion, objeto, detalle, hash_anterior, hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fecha, usuario, rol, accion, objeto, detalle, anterior, h))
        conn.commit()


def verificar_cadena(conn) -> dict:
    """Recalcula todos los hashes. Si una fila fue alterada, indica cuál."""
    anterior = None
    total = 0
    for r in conn.execute("SELECT * FROM auditoria ORDER BY id"):
        total += 1
        esperado = _hash_fila(anterior, r["fecha"], r["usuario"], r["rol"], r["accion"], r["objeto"], r["detalle"])
        if r["hash_anterior"] != anterior or r["hash"] != esperado:
            return {"integra": False, "total": total, "fila_alterada": r["id"]}
        anterior = r["hash"]
    return {"integra": True, "total": total, "fila_alterada": None, "ultimo_hash": anterior}
