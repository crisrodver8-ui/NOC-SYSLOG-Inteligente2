"""Pruebas de fechas inmutables, auditoría encadenada y migración desde v0.2.0 (hallazgo del Corte 2)."""
import sqlite3

import pytest

from conftest import cab


def _conn(app):
    from noc.db import connect
    return connect(app.config["DB_PATH"])


def _evento(cliente):
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "normal", "cantidad": 5})
    return cliente.get("/api/eventos", headers=cab()).json["items"][0]["id"]


@pytest.mark.parametrize("campo,valor", [("recibido_en", "2000-01-01T00:00:00"), ("fecha_evento", "2000-01-01T00:00:00"),
                                         ("mensaje", "alterado"), ("severidad", 7)])
def test_evento_no_se_puede_modificar(app, cliente, campo, valor):
    eid = _evento(cliente)
    conn = _conn(app)
    with pytest.raises(sqlite3.IntegrityError, match="inmutable"):
        conn.execute(f"UPDATE eventos SET {campo} = ? WHERE id = ?", (valor, eid))


def test_evento_no_se_puede_borrar(app, cliente):
    eid = _evento(cliente)
    with pytest.raises(sqlite3.IntegrityError):
        _conn(app).execute("DELETE FROM eventos WHERE id = ?", (eid,))


def test_auditoria_no_se_modifica_ni_borra(app, cliente):
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "normal", "cantidad": 2})
    conn = _conn(app)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE auditoria SET fecha = '2000-01-01T00:00:00'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM auditoria")


def test_fecha_creacion_incidente_inmutable(app, cliente):
    iid = cliente.post("/api/incidentes", headers=cab(), json={"titulo": "Prueba fecha", "severidad": 4}).json["id"]
    with pytest.raises(sqlite3.IntegrityError):
        _conn(app).execute("UPDATE incidentes SET creado_en = '2000-01-01T00:00:00' WHERE id = ?", (iid,))


def test_api_ignora_fechas_enviadas_por_el_usuario(cliente):
    r = cliente.post("/api/incidentes", headers=cab(),
                     json={"titulo": "Fecha falsa", "severidad": 4, "creado_en": "1999-01-01T00:00:00"})
    inc = cliente.get(f"/api/incidentes/{r.json['id']}", headers=cab()).json["incidente"]
    assert not inc["creado_en"].startswith("1999")


def test_accion_verificada_es_final(app, cliente):
    base = {"dispositivo_id": 1, "tipo": "observar", "justificacion": "Seguimiento del evento"}
    aid = cliente.post("/api/acciones", headers=cab(), json=base).json["id"]
    cliente.post(f"/api/acciones/{aid}/revisar", headers=cab("supervisor1"), json={"decision": "aprobar"})
    cliente.post(f"/api/acciones/{aid}/ejecutar", headers=cab(), json={})
    cliente.post(f"/api/acciones/{aid}/verificar", headers=cab(), json={"verificacion": "Sin cambios necesarios"})
    with pytest.raises(sqlite3.IntegrityError):
        _conn(app).execute("UPDATE acciones SET estado = 'propuesta' WHERE id = ?", (aid,))


def test_cadena_detecta_alteracion(app, cliente):
    from noc.db import verificar_cadena
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "ataque_ia"})
    conn = _conn(app)
    assert verificar_cadena(conn)["integra"] is True
    # Un atacante con acceso al archivo quita la protección y altera un registro...
    conn.execute("DROP TRIGGER auditoria_sin_update")
    victima = conn.execute("SELECT id FROM auditoria ORDER BY id LIMIT 1 OFFSET 2").fetchone()["id"]
    conn.execute("UPDATE auditoria SET detalle = 'borrado de huellas' WHERE id = ?", (victima,))
    conn.commit()
    # ...y la cadena de hashes lo delata
    r = verificar_cadena(conn)
    assert r["integra"] is False and r["fila_alterada"] == victima
    assert cliente.get("/api/integridad", headers=cab("auditor1")).json["integra"] is False


def test_ultima_vez_no_retrocede(app, cliente):
    eid = _evento(cliente)
    with pytest.raises(sqlite3.IntegrityError):
        _conn(app).execute("UPDATE eventos SET ultima_vez = '2000-01-01T00:00:00' WHERE id = ?", (eid,))


def test_migracion_desde_v020(tmp_path):
    """Una BD creada con v0.2.0 se actualiza sin perder datos y queda protegida."""
    ruta = tmp_path / "v020.db"
    viejo = sqlite3.connect(ruta)
    viejo.executescript("""
        CREATE TABLE dispositivos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL UNIQUE, ip TEXT NOT NULL UNIQUE,
            marca TEXT NOT NULL, modelo TEXT NOT NULL DEFAULT '', version TEXT NOT NULL DEFAULT '', ubicacion TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'activo', autorizado INTEGER NOT NULL DEFAULT 1, simulado INTEGER NOT NULL DEFAULT 1,
            actualizado_en TEXT NOT NULL);
        CREATE TABLE eventos (id INTEGER PRIMARY KEY AUTOINCREMENT, recibido_en TEXT NOT NULL, fecha_evento TEXT, ip_origen TEXT NOT NULL,
            hostname TEXT, dispositivo_id INTEGER, marca TEXT, facility INTEGER NOT NULL, facility_nombre TEXT NOT NULL,
            severidad INTEGER NOT NULL, app TEXT, mensaje TEXT NOT NULL, crudo TEXT NOT NULL, formato TEXT NOT NULL, origen TEXT NOT NULL,
            huella TEXT NOT NULL, repeticiones INTEGER NOT NULL DEFAULT 1, ultima_vez TEXT NOT NULL, banderas TEXT NOT NULL DEFAULT '',
            sospechoso INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE auditoria (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, usuario TEXT NOT NULL, rol TEXT NOT NULL,
            accion TEXT NOT NULL, objeto TEXT NOT NULL DEFAULT '', detalle TEXT NOT NULL DEFAULT '');
        INSERT INTO dispositivos (nombre, ip, marca, actualizado_en) VALUES ('VIEJO-RT', '192.0.2.1', 'Cisco', '2026-10-01T10:00:00');
        INSERT INTO auditoria (fecha, usuario, rol, accion) VALUES ('2026-10-01T10:00:00', 'operador1', 'operador', 'crear_dispositivo');
        INSERT INTO auditoria (fecha, usuario, rol, accion) VALUES ('2026-10-01T10:05:00', 'supervisor1', 'supervisor', 'accion_aprobada');
    """)
    viejo.close()
    from noc import db
    conn = db.connect(str(ruta))
    db.init_db(conn)
    assert conn.execute("SELECT nombre, gestion, consola_tipo FROM dispositivos").fetchone()["gestion"] == "ninguna"
    assert db.verificar_cadena(conn) == {**db.verificar_cadena(conn), "integra": True, "total": 2}
    assert conn.execute("SELECT version FROM esquema_version").fetchone()["version"] == "1.0.0"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM auditoria")
