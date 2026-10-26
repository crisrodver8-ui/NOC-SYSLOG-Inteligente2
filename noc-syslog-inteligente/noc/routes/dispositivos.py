"""
Inventario de equipos (CRUD), acceso de administración (consola y SSH)
y puertos/interfaces físicas de cada equipo.
"""
import ipaddress
import re
import sqlite3

from flask import Blueprint, current_app, g, jsonify

from .. import consola, gestor_remoto, interfaces
from ..db import ahora, filas, get_db, registrar_auditoria
from . import ErrorAPI, cuerpo_json, requiere

bp = Blueprint("dispositivos", __name__)

MARCAS = ("Cisco", "Fortinet", "Huawei", "Otro")
ESTADOS = ("activo", "inactivo", "mantenimiento")
VELOCIDADES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
_RE_SERIAL = re.compile(r"^(COM\d{1,3}|/dev/tty[\w.]+)$", re.I)
_RE_TELNET = re.compile(r"^([\w.\-]{1,63}):(\d{1,5})$")

CAMPOS = ("nombre", "ip", "marca", "modelo", "version", "ubicacion", "estado", "autorizado", "simulado",
          "gestion", "ssh_puerto", "consola_tipo", "consola_destino", "consola_velocidad")


def _validar(d: dict) -> dict:
    """Valida el formulario del equipo. Las fechas NUNCA se reciben: las pone el servidor."""
    nombre = str(d.get("nombre", "")).strip()
    if not re.match(r"^[\w.\-]{2,50}$", nombre):
        raise ErrorAPI("Nombre: 2 a 50 caracteres (letras, números, punto, guion o guion bajo).")
    try:
        ip = str(ipaddress.ip_address(str(d.get("ip", "")).strip()))
    except ValueError:
        raise ErrorAPI("IP inválida.")
    if d.get("marca") not in MARCAS:
        raise ErrorAPI(f"Marca inválida. Opciones: {', '.join(MARCAS)}.")
    if d.get("estado", "activo") not in ESTADOS:
        raise ErrorAPI(f"Estado inválido. Opciones: {', '.join(ESTADOS)}.")

    consola_tipo = d.get("consola_tipo", "ninguna")
    destino = str(d.get("consola_destino", "")).strip()
    if consola_tipo == "serial" and not _RE_SERIAL.match(destino):
        raise ErrorAPI("Consola serial: indica el puerto, ej. COM3 (Windows) o /dev/ttyUSB0 (Linux).")
    if consola_tipo == "telnet":
        m = _RE_TELNET.match(destino)
        if not m or not 1 <= int(m.group(2)) <= 65535:
            raise ErrorAPI("Consola telnet (GNS3/EVE-NG): formato host:puerto, ej. 127.0.0.1:5000.")
    if consola_tipo not in ("ninguna", "serial", "telnet"):
        raise ErrorAPI("Tipo de consola inválido.")
    if consola_tipo == "ninguna":
        destino = ""
    try:
        velocidad = int(d.get("consola_velocidad", 9600))
        ssh_puerto = int(d.get("ssh_puerto", 22))
    except (TypeError, ValueError):
        raise ErrorAPI("Velocidad y puerto SSH deben ser números.")
    if velocidad not in VELOCIDADES:
        raise ErrorAPI("Velocidad de consola inválida (lo normal es 9600).")
    if not 1 <= ssh_puerto <= 65535:
        raise ErrorAPI("Puerto SSH fuera de rango.")
    gestion = d.get("gestion", "ninguna")
    if gestion not in ("ninguna", "ssh", "consola"):
        raise ErrorAPI("Gestión remota inválida.")
    if gestion == "consola" and consola_tipo != "telnet":
        raise ErrorAPI("Para gestionar por consola, la consola debe ser telnet (GNS3/EVE-NG).")

    texto = lambda k: str(d.get(k, "")).strip()[:80]
    return {"nombre": nombre, "ip": ip, "marca": d["marca"], "modelo": texto("modelo"), "version": texto("version"),
            "ubicacion": texto("ubicacion"), "estado": d.get("estado", "activo"),
            "autorizado": int(bool(d.get("autorizado", True))), "simulado": int(bool(d.get("simulado", True))),
            "gestion": gestion, "ssh_puerto": ssh_puerto, "consola_tipo": consola_tipo,
            "consola_destino": destino, "consola_velocidad": velocidad}


def _equipo(db, id_):
    d = db.execute("SELECT * FROM dispositivos WHERE id = ?", (id_,)).fetchone()
    if not d:
        raise ErrorAPI("Equipo no encontrado.", 404)
    return d


@bp.get("/dispositivos")
@requiere()
def listar():
    """Inventario de equipos."""
    return jsonify(filas(get_db().execute(
        """SELECT d.*, (SELECT COUNT(*) FROM interfaces i WHERE i.dispositivo_id = d.id) AS puertos,
                  (SELECT COUNT(*) FROM interfaces i WHERE i.dispositivo_id = d.id AND i.estado = 'up') AS puertos_up
           FROM dispositivos d ORDER BY d.nombre""")))


@bp.get("/dispositivos/<int:id_>")
@requiere()
def detalle(id_):
    """Detalle del equipo con puertos, acceso de administración y últimos eventos."""
    db = get_db()
    d = dict(_equipo(db, id_))
    d["interfaces"] = filas(db.execute(
        "SELECT * FROM interfaces WHERE dispositivo_id = ? ORDER BY tipo = 'consola', tipo = 'gestion', id", (id_,)))
    d["eventos_recientes"] = filas(db.execute(
        """SELECT id, recibido_en, severidad, mensaje, banderas FROM eventos
           WHERE dispositivo_id = ? ORDER BY id DESC LIMIT 5""", (id_,)))
    usuario, clave = gestor_remoto.credenciales(current_app.config, d)
    d["credenciales_configuradas"] = bool(usuario and clave)   # nunca se devuelven las credenciales
    return jsonify(d)


@bp.post("/dispositivos")
@requiere("operador")
def crear():
    """Agrega un equipo al inventario."""
    v = _validar(cuerpo_json())
    db = get_db()
    try:
        cur = db.execute(
            f"INSERT INTO dispositivos ({', '.join(CAMPOS)}, actualizado_en) VALUES ({', '.join('?' * len(CAMPOS))}, ?)",
            (*[v[c] for c in CAMPOS], ahora()))
    except sqlite3.IntegrityError:
        raise ErrorAPI("Ya existe un equipo con ese nombre o IP.", 409)
    registrar_auditoria(db, g.usuario, g.rol, "crear_dispositivo", f"dispositivo #{cur.lastrowid}",
                        f"{v['nombre']} {v['ip']} ({v['marca']}) gestión={v['gestion']}")
    return jsonify(id=cur.lastrowid), 201


@bp.put("/dispositivos/<int:id_>")
@requiere("operador")
def editar(id_):
    """Edita un equipo."""
    v = _validar(cuerpo_json())
    db = get_db()
    anterior = _equipo(db, id_)
    try:
        db.execute(f"UPDATE dispositivos SET {', '.join(c + '=?' for c in CAMPOS)}, actualizado_en=? WHERE id=?",
                   (*[v[c] for c in CAMPOS], ahora(), id_))
    except sqlite3.IntegrityError:
        raise ErrorAPI("Ya existe un equipo con ese nombre o IP.", 409)
    cambios = [f"{c}: {anterior[c]} → {v[c]}" for c in CAMPOS if str(anterior[c]) != str(v[c])]
    registrar_auditoria(db, g.usuario, g.rol, "editar_dispositivo", f"dispositivo #{id_}",
                        f"{v['nombre']}: " + ("; ".join(cambios) or "sin cambios"))
    return jsonify(ok=True)


@bp.delete("/dispositivos/<int:id_>")
@requiere("supervisor")
def eliminar(id_):
    """Elimina un equipo (solo supervisor)."""
    db = get_db()
    fila = _equipo(db, id_)
    if db.execute("SELECT 1 FROM acciones WHERE dispositivo_id = ? LIMIT 1", (id_,)).fetchone():
        raise ErrorAPI("El equipo tiene acciones registradas; márcalo como inactivo en lugar de borrarlo.", 409)
    db.execute("DELETE FROM dispositivos WHERE id = ?", (id_,))
    registrar_auditoria(db, g.usuario, g.rol, "eliminar_dispositivo", f"dispositivo #{id_}", f"{fila['nombre']} {fila['ip']}")
    return jsonify(ok=True)


# ------------------------------------------------------------- interfaces
def _validar_interfaz(d: dict) -> dict:
    nombre = str(d.get("nombre", "")).strip()
    if not re.match(r"^[\w/.:\-]{1,60}$", nombre):
        raise ErrorAPI("Nombre de puerto inválido (ej. GigabitEthernet0/1, wan1, Console).")
    tipo = d.get("tipo", "cobre")
    estado = d.get("estado", "desconocido")
    if tipo not in ("cobre", "fibra", "consola", "gestion", "virtual"):
        raise ErrorAPI("Tipo de puerto inválido.")
    if estado not in ("up", "down", "admin_down", "desconocido"):
        raise ErrorAPI("Estado de puerto inválido.")
    ip = str(d.get("ip", "")).strip()
    if ip:
        try:
            ip = str(ipaddress.ip_interface(ip))
        except ValueError:
            raise ErrorAPI("IP del puerto inválida (ej. 192.168.1.1/24).")
    texto = lambda k, n=60: str(d.get(k, "")).strip()[:n]
    return {"nombre": nombre, "nombre_norm": interfaces.normalizar(nombre), "tipo": tipo, "estado": estado,
            "velocidad": texto("velocidad", 10), "ip": ip, "vlan": texto("vlan", 20),
            "descripcion": texto("descripcion", 120), "conectado_a": texto("conectado_a", 80)}


@bp.post("/dispositivos/<int:id_>/interfaces")
@requiere("operador")
def crear_interfaz(id_):
    """Agrega un puerto al equipo."""
    db = get_db()
    disp = _equipo(db, id_)
    v = _validar_interfaz(cuerpo_json())
    try:
        cur = db.execute(
            """INSERT INTO interfaces (dispositivo_id, nombre, nombre_norm, tipo, estado, velocidad, ip, vlan,
                   descripcion, conectado_a, origen, actualizado_en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', ?)""",
            (id_, *v.values(), ahora()))
    except sqlite3.IntegrityError:
        raise ErrorAPI("Ese puerto ya existe en el equipo.", 409)
    registrar_auditoria(db, g.usuario, g.rol, "crear_puerto", disp["nombre"], v["nombre"])
    return jsonify(id=cur.lastrowid), 201


@bp.put("/interfaces/<int:iid>")
@requiere("operador")
def editar_interfaz(iid):
    """Edita un puerto."""
    db = get_db()
    fila = db.execute("SELECT i.*, d.nombre AS equipo FROM interfaces i JOIN dispositivos d ON d.id = i.dispositivo_id WHERE i.id = ?",
                      (iid,)).fetchone()
    if not fila:
        raise ErrorAPI("Puerto no encontrado.", 404)
    v = _validar_interfaz(cuerpo_json())
    try:
        db.execute(f"UPDATE interfaces SET {', '.join(k + '=?' for k in v)}, actualizado_en=? WHERE id=?",
                   (*v.values(), ahora(), iid))
    except sqlite3.IntegrityError:
        raise ErrorAPI("Ya existe otro puerto con ese nombre.", 409)
    registrar_auditoria(db, g.usuario, g.rol, "editar_puerto", fila["equipo"], f"{fila['nombre']} → {v['nombre']} ({v['estado']})")
    return jsonify(ok=True)


@bp.delete("/interfaces/<int:iid>")
@requiere("operador")
def eliminar_interfaz(iid):
    """Elimina un puerto."""
    db = get_db()
    fila = db.execute("SELECT i.nombre, d.nombre AS equipo FROM interfaces i JOIN dispositivos d ON d.id = i.dispositivo_id WHERE i.id = ?",
                      (iid,)).fetchone()
    if not fila:
        raise ErrorAPI("Puerto no encontrado.", 404)
    db.execute("DELETE FROM interfaces WHERE id = ?", (iid,))
    registrar_auditoria(db, g.usuario, g.rol, "eliminar_puerto", fila["equipo"], fila["nombre"])
    return jsonify(ok=True)


@bp.post("/dispositivos/<int:id_>/interfaces/sincronizar")
@requiere("operador")
def sincronizar_interfaces(id_):
    """Lee los puertos REALES del equipo (SSH o consola) con un comando de consulta permitido."""
    db = get_db()
    disp = dict(_equipo(db, id_))
    comando = interfaces.COMANDO_INTERFACES.get(disp["marca"])
    if not comando or not consola.validar(disp["marca"], comando)[0]:
        raise ErrorAPI("No hay comando de interfaces permitido para esta marca.")
    try:
        salida = gestor_remoto.ejecutar_consulta(current_app.config, disp, comando)
    except gestor_remoto.ErrorGestion as e:
        registrar_auditoria(db, g.usuario, g.rol, "sincronizar_puertos_error", disp["nombre"], str(e))
        raise ErrorAPI(str(e), 502)
    puertos = interfaces.parsear_salida(disp["marca"], salida)
    nuevos = actualizados = 0
    for p in puertos:
        norm = interfaces.normalizar(p["nombre"])
        fila = db.execute("SELECT id FROM interfaces WHERE dispositivo_id = ? AND nombre_norm = ?", (id_, norm)).fetchone()
        if fila:
            db.execute("UPDATE interfaces SET estado = ?, ip = CASE WHEN ? != '' THEN ? ELSE ip END, actualizado_en = ? WHERE id = ?",
                       (p["estado"], p["ip"], p["ip"], ahora(), fila["id"]))
            actualizados += 1
        else:
            tipo = "virtual" if re.match(r"(loopback|vlan|null|tunnel)", norm) else "cobre"
            db.execute("""INSERT INTO interfaces (dispositivo_id, nombre, nombre_norm, tipo, estado, ip, origen, actualizado_en)
                          VALUES (?, ?, ?, ?, ?, ?, 'ssh', ?)""", (id_, p["nombre"], norm, tipo, p["estado"], p["ip"], ahora()))
            nuevos += 1
    registrar_auditoria(db, g.usuario, g.rol, "sincronizar_puertos", disp["nombre"],
                        f"{comando}: {len(puertos)} puertos ({nuevos} nuevos, {actualizados} actualizados)")
    return jsonify(comando=comando, leidos=len(puertos), nuevos=nuevos, actualizados=actualizados)


@bp.post("/dispositivos/<int:id_>/probar")
@requiere("operador")
def probar_conexion(id_):
    """Prueba la conexión real ejecutando un comando de consulta inofensivo."""
    db = get_db()
    disp = dict(_equipo(db, id_))
    comando = {"Cisco": "show clock", "Huawei": "display clock", "Fortinet": "get system status"}.get(disp["marca"], "date")
    try:
        salida = gestor_remoto.ejecutar_consulta(current_app.config, disp, comando)
        ok, detalle = True, salida[:500]
    except gestor_remoto.ErrorGestion as e:
        ok, detalle = False, str(e)
    registrar_auditoria(db, g.usuario, g.rol, "probar_conexion", disp["nombre"], f"{'OK' if ok else 'FALLÓ'}: {detalle[:200]}")
    return jsonify(ok=ok, comando=comando, detalle=detalle)
