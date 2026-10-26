"""
Acciones de respuesta con el FLUJO SEGURO obligatorio:

  evento detectado -> validación -> propuesta de acción -> revisión humana
  -> aprobación -> ejecución autorizada -> verificación -> auditoría

Reglas:
  * El comando sale del catálogo cerrado (catalogo_acciones), nunca del texto del log.
  * Quien propone NO puede aprobar su propia acción (principio de cuatro ojos).
  * Solo el rol supervisor aprueba o rechaza.
  * Solo se ejecuta lo aprobado: simulado en equipos simulados y REAL (SSH/consola) en equipos de laboratorio.
  * Cada paso queda en la auditoría.
"""
from flask import Blueprint, current_app, g, jsonify

from .. import gestor_remoto
from ..catalogo_acciones import CATALOGO, AccionInvalida, construir_comando
from ..db import ahora, filas, get_db, registrar_auditoria
from . import ErrorAPI, cuerpo_json, requiere

bp = Blueprint("acciones", __name__)


def _accion(db, id_):
    a = db.execute("SELECT * FROM acciones WHERE id = ?", (id_,)).fetchone()
    if not a:
        raise ErrorAPI("Acción no encontrada.", 404)
    return a


@bp.get("/acciones/catalogo")
@requiere()
def catalogo():
    """Catálogo cerrado de acciones permitidas."""
    return jsonify({k: {"nombre": v["nombre"], "parametro": v["parametro"]} for k, v in CATALOGO.items()})


@bp.get("/acciones")
@requiere()
def listar():
    """Lista de acciones con su estado en el flujo seguro."""
    return jsonify(filas(get_db().execute(
        """SELECT a.*, d.nombre AS dispositivo, d.marca FROM acciones a
           JOIN dispositivos d ON d.id = a.dispositivo_id
           ORDER BY CASE a.estado WHEN 'propuesta' THEN 0 WHEN 'aprobada' THEN 1 WHEN 'ejecutada' THEN 2 ELSE 3 END,
                    a.id DESC""")))


@bp.post("/acciones")
@requiere("operador")
def proponer():
    """PROPUESTA de acción (validada contra el catálogo)."""
    d = cuerpo_json()
    db = get_db()
    disp = db.execute("SELECT * FROM dispositivos WHERE id = ?", (d.get("dispositivo_id"),)).fetchone()
    # --- VALIDACIÓN ---
    if not disp:
        raise ErrorAPI("Selecciona un equipo del inventario.")
    if not disp["autorizado"]:
        raise ErrorAPI("El equipo no está en la lista permitida; no se pueden proponer acciones sobre él.")
    justificacion = str(d.get("justificacion", "")).strip()
    if len(justificacion) < 10:
        raise ErrorAPI("Escribe una justificación (mínimo 10 caracteres).")
    try:
        comando = construir_comando(d.get("tipo"), disp["marca"], d.get("parametro"))
    except AccionInvalida as e:
        raise ErrorAPI(str(e))
    # --- PROPUESTA ---
    cur = db.execute(
        """INSERT INTO acciones (evento_id, incidente_id, dispositivo_id, tipo, parametro, comando,
               justificacion, estado, propuesta_por, creado_en, actualizado_en)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'propuesta', ?, ?, ?)""",
        (d.get("evento_id") or None, d.get("incidente_id") or None, disp["id"], d["tipo"],
         d.get("parametro") or None, comando, justificacion[:1000], g.usuario, ahora(), ahora()))
    registrar_auditoria(db, g.usuario, g.rol, "proponer_accion", f"acción #{cur.lastrowid}",
                        f"{CATALOGO[d['tipo']]['nombre']} en {disp['nombre']}")
    db.commit()
    return jsonify(id=cur.lastrowid, comando=comando), 201


@bp.post("/acciones/<int:id_>/revisar")
@requiere("supervisor")
def revisar(id_):
    """REVISIÓN HUMANA y APROBACIÓN (o rechazo)."""
    d = cuerpo_json()
    db = get_db()
    a = _accion(db, id_)
    if a["estado"] != "propuesta":
        raise ErrorAPI("Solo se revisan acciones en estado 'propuesta'.")
    if a["propuesta_por"] == g.usuario:
        raise ErrorAPI("Quien propone una acción no puede aprobarla (cuatro ojos).", 403)
    decision = d.get("decision")
    if decision not in ("aprobar", "rechazar"):
        raise ErrorAPI("La decisión debe ser 'aprobar' o 'rechazar'.")
    comentario = str(d.get("comentario", "")).strip()
    if decision == "rechazar" and not comentario:
        raise ErrorAPI("Explica el motivo del rechazo.")
    nuevo = "aprobada" if decision == "aprobar" else "rechazada"
    db.execute("UPDATE acciones SET estado=?, revisada_por=?, comentario_revision=?, actualizado_en=? WHERE id=?",
               (nuevo, g.usuario, comentario[:500], ahora(), id_))
    registrar_auditoria(db, g.usuario, g.rol, f"accion_{nuevo}", f"acción #{id_}", comentario)
    db.commit()
    return jsonify(estado=nuevo)


@bp.post("/acciones/<int:id_>/ejecutar")
@requiere("operador")
def ejecutar(id_):
    """
    EJECUCIÓN AUTORIZADA.
    - Equipo simulado: se registra una ejecución simulada.
    - Equipo real (GNS3/laboratorio): se envían las líneas por SSH o consola desde el backend.
    """
    db = get_db()
    a = _accion(db, id_)
    if a["estado"] != "aprobada":
        raise ErrorAPI("Solo se ejecutan acciones APROBADAS por un supervisor.", 403)
    disp = dict(db.execute("SELECT * FROM dispositivos WHERE id = ?", (a["dispositivo_id"],)).fetchone())
    if not disp["autorizado"]:
        raise ErrorAPI("El equipo salió de la lista permitida después de la aprobación. Ejecución bloqueada.", 403)
    lineas = [l for l in a["comando"].splitlines() if l.strip() and not l.lstrip().startswith("!")]
    if disp["simulado"] or not lineas:
        resultado = (f"[{'SIMULADO' if disp['simulado'] else 'SIN CAMBIOS'}] {disp['nombre']} ({disp['ip']}) "
                     f"por {g.usuario}.\n{a['comando']}\nRespuesta: OK")
    else:
        modo = CATALOGO.get(a["tipo"], {}).get("modo", "config")
        try:
            transcripcion = gestor_remoto.ejecutar_cambio(current_app.config, disp, lineas, modo=modo)
        except gestor_remoto.ErrorGestion as e:
            registrar_auditoria(db, g.usuario, g.rol, "ejecutar_accion_error", f"acción #{id_}", str(e)[:500])
            raise ErrorAPI(f"La ejecución falló y la acción sigue aprobada: {e}", 502)
        resultado = f"[REAL] {disp['nombre']} ({disp['ip']}) por {g.usuario}.\n{transcripcion}"
    db.execute("UPDATE acciones SET estado='ejecutada', ejecutada_por=?, resultado=?, actualizado_en=? WHERE id=?",
               (g.usuario, resultado[:20000], ahora(), id_))
    registrar_auditoria(db, g.usuario, g.rol, "ejecutar_accion", f"acción #{id_}", a["comando"])
    return jsonify(estado="ejecutada", resultado=resultado)


@bp.post("/acciones/<int:id_>/verificar")
@requiere("operador")
def verificar(id_):
    """VERIFICACIÓN: alguien confirma que la acción tuvo el efecto esperado."""
    d = cuerpo_json()
    db = get_db()
    a = _accion(db, id_)
    if a["estado"] != "ejecutada":
        raise ErrorAPI("Solo se verifican acciones ejecutadas.")
    nota = str(d.get("verificacion", "")).strip()
    if len(nota) < 5:
        raise ErrorAPI("Describe cómo verificaste el resultado.")
    exito = bool(d.get("exito", True))
    texto = f"{'ÉXITO' if exito else 'FALLÓ'}: {nota}"
    db.execute("UPDATE acciones SET estado='verificada', verificada_por=?, verificacion=?, actualizado_en=? WHERE id=?",
               (g.usuario, texto[:1000], ahora(), id_))
    registrar_auditoria(db, g.usuario, g.rol, "verificar_accion", f"acción #{id_}", texto)
    db.commit()
    return jsonify(estado="verificada")
