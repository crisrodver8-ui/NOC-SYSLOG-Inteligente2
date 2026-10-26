"""Eventos Syslog: consulta con filtros, detalle, importación de archivos y simulador."""
from flask import Blueprint, current_app, g, jsonify, request

from .. import simulador
from ..db import filas, get_db, registrar_auditoria
from . import ErrorAPI, requiere

bp = Blueprint("eventos", __name__)


def _filtros() -> tuple[str, list]:
    """Arma el WHERE de forma segura (siempre con parámetros '?', nunca concatenando valores)."""
    a = request.args
    condiciones, params = [], []
    if a.get("desde"):
        condiciones.append("e.recibido_en >= ?"); params.append(a["desde"])
    if a.get("hasta"):
        hasta = a["hasta"] + ("T23:59:59" if len(a["hasta"]) == 10 else "")
        condiciones.append("e.recibido_en <= ?"); params.append(hasta)
    if a.get("marca"):
        condiciones.append("e.marca = ?"); params.append(a["marca"])
    if a.get("dispositivo_id"):
        condiciones.append("e.dispositivo_id = ?"); params.append(int(a["dispositivo_id"]))
    if a.get("severidad", "") != "":
        condiciones.append("e.severidad = ?"); params.append(int(a["severidad"]))
    if a.get("sev_max", "") != "":
        condiciones.append("e.severidad <= ?"); params.append(int(a["sev_max"]))
    if a.get("riesgo_min", "") != "":
        condiciones.append("e.riesgo >= ?"); params.append(int(a["riesgo_min"]))
    if a.get("sospechoso") == "1":
        condiciones.append("e.sospechoso = 1")
    if a.get("texto"):
        condiciones.append("(e.mensaje LIKE ? OR e.hostname LIKE ? OR e.ip_origen LIKE ?)")
        params += [f"%{a['texto']}%"] * 3
    return ("WHERE " + " AND ".join(condiciones)) if condiciones else "", params


@bp.get("/eventos")
@requiere()
def listar():
    """Eventos con filtros (desde, hasta, marca, dispositivo_id, severidad, sev_max, riesgo_min, sospechoso, texto)."""
    try:
        where, params = _filtros()
        limite = min(int(request.args.get("limite", 50)), 500)
        desplazamiento = max(int(request.args.get("desplazamiento", 0)), 0)
    except ValueError:
        raise ErrorAPI("Filtro con valor numérico inválido.")
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM eventos e {where}", params).fetchone()[0]
    items = filas(db.execute(
        f"""SELECT e.id, e.recibido_en, e.fecha_evento, e.ip_origen, e.hostname, e.marca, e.severidad,
                   e.facility_nombre, e.app, e.mensaje, e.repeticiones, e.banderas, e.sospechoso, e.origen, e.riesgo, e.desfase_s,
                   d.nombre AS dispositivo
            FROM eventos e LEFT JOIN dispositivos d ON d.id = e.dispositivo_id
            {where} ORDER BY e.id DESC LIMIT ? OFFSET ?""", [*params, limite, desplazamiento]))
    return jsonify(total=total, items=items)


@bp.get("/eventos/<int:id_>")
@requiere()
def detalle(id_):
    """Detalle de un evento, incluido el mensaje original."""
    fila = get_db().execute(
        """SELECT e.*, d.nombre AS dispositivo FROM eventos e
           LEFT JOIN dispositivos d ON d.id = e.dispositivo_id WHERE e.id = ?""", (id_,)).fetchone()
    if not fila:
        raise ErrorAPI("Evento no encontrado.", 404)
    return jsonify(dict(fila))


@bp.post("/eventos/importar")
@requiere("operador")
def importar():
    """Importa un archivo de texto con un mensaje Syslog por línea."""
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        raise ErrorAPI("Adjunta un archivo .log o .txt.")
    if not archivo.filename.lower().endswith((".log", ".txt")):
        raise ErrorAPI("Solo se aceptan archivos .log o .txt.")
    texto = archivo.read().decode("utf-8", errors="replace")
    lineas = [l for l in texto.splitlines() if l.strip()]
    if len(lineas) > 5000:
        raise ErrorAPI("Máximo 5000 líneas por importación.")
    db, ingestor = get_db(), current_app.extensions["ingestor"]
    resumen = {"lineas": len(lineas), "almacenado": 0, "duplicado": 0, "otros": 0}
    for linea in lineas:
        r = ingestor.procesar(db, linea, "importado", "importacion")
        clave = r["estado"] if r["estado"] in resumen else "otros"
        resumen[clave] += 1
    registrar_auditoria(db, g.usuario, g.rol, "importar_syslog", archivo.filename[:80],
                        f"{resumen['lineas']} líneas, {resumen['almacenado']} nuevos, {resumen['duplicado']} duplicados")
    db.commit()
    return jsonify(resumen)


@bp.post("/simulador")
@requiere("operador")
def simular():
    """Genera eventos simulados (normal, ataque_ia, tormenta)."""
    datos = request.get_json(silent=True) or {}
    escenario = datos.get("escenario", "normal")
    db, ingestor = get_db(), current_app.extensions["ingestor"]
    dispositivos = filas(db.execute("SELECT * FROM dispositivos WHERE autorizado = 1 AND ip != '127.0.0.1'"))
    if not dispositivos:
        raise ErrorAPI("No hay equipos autorizados en el inventario para simular.")
    if escenario == "normal":
        mensajes = simulador.escenario_normal(dispositivos, min(int(datos.get("cantidad", 25)), 200))
    elif escenario == "ataque_ia":
        mensajes = simulador.escenario_ataque_ia(dispositivos)
    elif escenario == "tormenta":
        mensajes = simulador.escenario_tormenta(dispositivos)
    else:
        raise ErrorAPI("Escenario desconocido (normal, ataque_ia, tormenta).")
    conteo: dict[str, int] = {}
    for texto, ip in mensajes:
        estado = ingestor.procesar(db, texto, ip, "simulador")["estado"]
        conteo[estado] = conteo.get(estado, 0) + 1
    registrar_auditoria(db, g.usuario, g.rol, "simulador", escenario, str(conteo))
    db.commit()
    return jsonify(escenario=escenario, enviados=len(mensajes), resultado=conteo)
