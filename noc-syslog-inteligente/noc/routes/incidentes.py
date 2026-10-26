"""Incidentes: creación, asignación, seguimiento (notas) y cierre."""
from flask import Blueprint, g, jsonify, request

from ..db import ahora, filas, get_db, registrar_auditoria
from . import ErrorAPI, cuerpo_json, requiere

bp = Blueprint("incidentes", __name__)

ESTADOS = ("abierto", "en_progreso", "resuelto", "cerrado")
# Transiciones válidas del ciclo de vida
TRANSICIONES = {
    "abierto": {"en_progreso", "cerrado"},
    "en_progreso": {"resuelto", "abierto"},
    "resuelto": {"cerrado", "en_progreso"},
    "cerrado": {"en_progreso"},  # reapertura
}


def _nota(db, inc_id, texto):
    db.execute("INSERT INTO incidente_notas (incidente_id, autor, nota, creado_en) VALUES (?, ?, ?, ?)",
               (inc_id, g.usuario, texto[:2000], ahora()))


def _validar_asignado(nombre):
    """Solo se asigna a usuarios activos que pueden trabajar incidentes (no auditores)."""
    if nombre and not get_db().execute(
            "SELECT 1 FROM usuarios WHERE usuario = ? AND activo = 1 AND rol != 'auditor'", (nombre,)).fetchone():
        raise ErrorAPI("Solo se puede asignar a un usuario activo (operador, supervisor o admin).")


@bp.get("/incidentes")
@requiere()
def listar():
    """Incidentes (filtro estado=activos|abierto|en_progreso|resuelto|cerrado)."""
    estado = request.args.get("estado")
    sql = """SELECT i.*, d.nombre AS dispositivo,
                    (SELECT COUNT(*) FROM incidente_notas n WHERE n.incidente_id = i.id) AS notas
             FROM incidentes i LEFT JOIN dispositivos d ON d.id = i.dispositivo_id"""
    params = []
    if estado == "activos":
        sql += " WHERE i.estado IN ('abierto','en_progreso')"
    elif estado in ESTADOS:
        sql += " WHERE i.estado = ?"; params.append(estado)
    sql += " ORDER BY CASE i.estado WHEN 'abierto' THEN 0 WHEN 'en_progreso' THEN 1 WHEN 'resuelto' THEN 2 ELSE 3 END, i.severidad, i.id DESC"
    return jsonify(filas(get_db().execute(sql, params)))


@bp.get("/incidentes/<int:id_>")
@requiere()
def detalle(id_):
    """Detalle de un incidente con notas y acciones."""
    db = get_db()
    inc = db.execute("""SELECT i.*, d.nombre AS dispositivo FROM incidentes i
                        LEFT JOIN dispositivos d ON d.id = i.dispositivo_id WHERE i.id = ?""", (id_,)).fetchone()
    if not inc:
        raise ErrorAPI("Incidente no encontrado.", 404)
    notas = filas(db.execute("SELECT * FROM incidente_notas WHERE incidente_id = ? ORDER BY id", (id_,)))
    acciones = filas(db.execute("SELECT * FROM acciones WHERE incidente_id = ? ORDER BY id", (id_,)))
    return jsonify(incidente=dict(inc), notas=notas, acciones=acciones)


@bp.post("/incidentes")
@requiere("operador")
def crear():
    """Crea un incidente."""
    d = cuerpo_json()
    titulo = str(d.get("titulo", "")).strip()
    if not 4 <= len(titulo) <= 150:
        raise ErrorAPI("El título debe tener entre 4 y 150 caracteres.")
    try:
        sev = int(d.get("severidad", 4))
        assert 0 <= sev <= 7
    except (ValueError, AssertionError):
        raise ErrorAPI("Severidad debe estar entre 0 y 7.")
    asignado = d.get("asignado_a") or None
    _validar_asignado(asignado)
    db = get_db()
    evento_id = d.get("evento_id") or None
    dispositivo_id = d.get("dispositivo_id") or None
    if evento_id and not dispositivo_id:
        ev = db.execute("SELECT dispositivo_id FROM eventos WHERE id = ?", (evento_id,)).fetchone()
        dispositivo_id = ev["dispositivo_id"] if ev else None
    cur = db.execute(
        """INSERT INTO incidentes (titulo, descripcion, severidad, estado, asignado_a, creado_por,
               evento_id, dispositivo_id, creado_en, actualizado_en)
           VALUES (?, ?, ?, 'abierto', ?, ?, ?, ?, ?, ?)""",
        (titulo, str(d.get("descripcion", ""))[:2000], sev, asignado, g.usuario,
         evento_id, dispositivo_id, ahora(), ahora()))
    _nota(db, cur.lastrowid, f"Incidente creado{' y asignado a ' + asignado if asignado else ''}.")
    registrar_auditoria(db, g.usuario, g.rol, "crear_incidente", f"incidente #{cur.lastrowid}", titulo)
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@bp.patch("/incidentes/<int:id_>")
@requiere("operador")
def actualizar(id_):
    """Asigna o cambia el estado de un incidente."""
    d = cuerpo_json()
    db = get_db()
    inc = db.execute("SELECT * FROM incidentes WHERE id = ?", (id_,)).fetchone()
    if not inc:
        raise ErrorAPI("Incidente no encontrado.", 404)
    cambios = []

    if "asignado_a" in d and (d["asignado_a"] or None) != inc["asignado_a"]:
        _validar_asignado(d["asignado_a"])
        db.execute("UPDATE incidentes SET asignado_a = ? WHERE id = ?", (d["asignado_a"] or None, id_))
        cambios.append(f"Asignado a {d['asignado_a'] or 'nadie'}")

    nuevo = d.get("estado")
    if nuevo and nuevo != inc["estado"]:
        if nuevo not in TRANSICIONES.get(inc["estado"], set()):
            raise ErrorAPI(f"No se puede pasar de '{inc['estado']}' a '{nuevo}'.")
        solucion = str(d.get("solucion", "")).strip()
        if nuevo in ("resuelto", "cerrado") and not (solucion or inc["solucion"]):
            raise ErrorAPI("Para resolver o cerrar describe la solución aplicada.")
        db.execute("UPDATE incidentes SET estado = ?, solucion = COALESCE(NULLIF(?, ''), solucion), cerrado_en = ? WHERE id = ?",
                   (nuevo, solucion, ahora() if nuevo == "cerrado" else None, id_))
        cambios.append(f"Estado: {inc['estado']} → {nuevo}" + (f". Solución: {solucion}" if solucion else ""))

    if not cambios:
        raise ErrorAPI("No hay cambios para guardar.")
    db.execute("UPDATE incidentes SET actualizado_en = ? WHERE id = ?", (ahora(), id_))
    for c in cambios:
        _nota(db, id_, c)
    registrar_auditoria(db, g.usuario, g.rol, "actualizar_incidente", f"incidente #{id_}", " | ".join(cambios))
    db.commit()
    return jsonify(ok=True)


@bp.post("/incidentes/<int:id_>/notas")
@requiere("operador")
def agregar_nota(id_):
    """Agrega una nota de seguimiento."""
    texto = str(cuerpo_json().get("nota", "")).strip()
    if not texto:
        raise ErrorAPI("La nota está vacía.")
    db = get_db()
    if not db.execute("SELECT 1 FROM incidentes WHERE id = ?", (id_,)).fetchone():
        raise ErrorAPI("Incidente no encontrado.", 404)
    _nota(db, id_, texto)
    db.execute("UPDATE incidentes SET actualizado_en = ? WHERE id = ?", (ahora(), id_))
    db.commit()
    return jsonify(ok=True), 201
