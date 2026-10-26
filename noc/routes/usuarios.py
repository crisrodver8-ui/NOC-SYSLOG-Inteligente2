"""Inicio de sesión, gestión de usuarios (admin) y tokens de la API."""
from flask import Blueprint, current_app, g, jsonify, request, session

from .. import autenticacion as auth
from ..db import filas, get_db, registrar_auditoria
from . import ErrorAPI, cuerpo_json, requiere

bp = Blueprint("usuarios", __name__)


def _datos_publicos(u) -> dict:
    return {"id": u["id"], "usuario": u["usuario"], "nombre": u["nombre"], "rol": u["rol"],
            "debe_cambiar_clave": bool(u["debe_cambiar_clave"]), "ultimo_acceso": u["ultimo_acceso"]}


def _abrir_sesion(u):
    session.clear()
    session.permanent = True
    session["uid"] = u["id"]
    # Si la clave cambia, todas las sesiones anteriores quedan inválidas
    session["version_clave"] = u["clave_hash"][-12:]


# ---------------------------------------------------------------- sesión
@bp.get("/sesion")
def estado_sesion():
    """Estado de la sesión actual."""
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0:
        return jsonify(autenticado=False, configuracion_inicial=True)
    uid = session.get("uid")
    u = db.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)).fetchone() if uid else None
    if not u or session.get("version_clave") != u["clave_hash"][-12:]:
        return jsonify(autenticado=False, configuracion_inicial=False)
    return jsonify(autenticado=True, usuario=_datos_publicos(u))


@bp.post("/sesion/inicial")
def configuracion_inicial():
    """Solo funciona cuando NO existe ningún usuario: crea el primer administrador."""
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] > 0:
        raise ErrorAPI("La configuración inicial ya se realizó.", 403)
    d = cuerpo_json()
    try:
        uid = auth.crear_usuario(db, d.get("usuario", ""), d.get("nombre", ""), "admin", d.get("clave", ""),
                                 "configuracion_inicial", debe_cambiar=False)
    except auth.ErrorAutenticacion as e:
        raise ErrorAPI(str(e))
    u = db.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone()
    registrar_auditoria(db, u["usuario"], "admin", "configuracion_inicial", f"usuario #{uid}", "Primer administrador creado")
    _abrir_sesion(u)
    return jsonify(usuario=_datos_publicos(u)), 201


@bp.post("/sesion/login")
def login():
    """Inicia sesión con usuario y clave."""
    d = cuerpo_json()
    db, cfg = get_db(), current_app.config
    nombre = str(d.get("usuario", ""))[:40]
    try:
        u = auth.iniciar_sesion(db, nombre, d.get("clave", ""), cfg["INTENTOS_LOGIN_MAX"], cfg["BLOQUEO_MINUTOS"])
    except auth.ErrorAutenticacion as e:
        registrar_auditoria(db, nombre or "(vacío)", "-", "login_fallido", request.remote_addr or "", str(e))
        raise ErrorAPI(str(e), 401)
    _abrir_sesion(u)
    registrar_auditoria(db, u["usuario"], u["rol"], "login", request.remote_addr or "", "Inicio de sesión")
    return jsonify(usuario=_datos_publicos(u))


@bp.post("/sesion/logout")
def logout():
    """Cierra la sesión."""
    uid = session.get("uid")
    if uid:
        db = get_db()
        u = db.execute("SELECT usuario, rol FROM usuarios WHERE id = ?", (uid,)).fetchone()
        if u:
            registrar_auditoria(db, u["usuario"], u["rol"], "logout", "", "Cierre de sesión")
    session.clear()
    return jsonify(ok=True)


@bp.post("/sesion/clave")
@requiere(permitir_cambio_pendiente=True)
def cambiar_mi_clave():
    """Cambia la clave del usuario actual."""
    d = cuerpo_json()
    db = get_db()
    try:
        auth.cambiar_clave(db, g.uid, d.get("actual", ""), d.get("nueva", ""))
    except auth.ErrorAutenticacion as e:
        raise ErrorAPI(str(e))
    u = db.execute("SELECT * FROM usuarios WHERE id = ?", (g.uid,)).fetchone()
    _abrir_sesion(u)  # nueva versión de clave en la sesión actual
    registrar_auditoria(db, g.usuario, g.rol, "cambio_clave", f"usuario #{g.uid}", "El usuario cambió su clave")
    return jsonify(ok=True)


# ---------------------------------------------------------------- usuarios
@bp.get("/usuarios/nombres")
@requiere()
def nombres():
    """Lista corta para asignar incidentes (cualquier usuario autenticado)."""
    return jsonify(filas(get_db().execute(
        "SELECT usuario, nombre, rol FROM usuarios WHERE activo = 1 ORDER BY rol, usuario")))


@bp.get("/usuarios")
@requiere("admin")
def listar():
    """Lista de usuarios (admin)."""
    return jsonify(filas(get_db().execute(
        """SELECT id, usuario, nombre, rol, activo, debe_cambiar_clave, intentos_fallidos, bloqueado_hasta,
                  ultimo_acceso, creado_por, creado_en FROM usuarios ORDER BY usuario""")))


@bp.post("/usuarios")
@requiere("admin")
def crear():
    """Crea un usuario con clave TEMPORAL que se muestra una sola vez."""
    d = cuerpo_json()
    db = get_db()
    temporal = auth.clave_temporal()
    try:
        uid = auth.crear_usuario(db, d.get("usuario", ""), d.get("nombre", ""), d.get("rol", ""), temporal, g.usuario)
    except auth.ErrorAutenticacion as e:
        raise ErrorAPI(str(e))
    registrar_auditoria(db, g.usuario, g.rol, "crear_usuario", f"usuario #{uid}",
                        f"{d.get('usuario')} con rol {d.get('rol')} (clave temporal)")
    return jsonify(id=uid, clave_temporal=temporal), 201


@bp.patch("/usuarios/<int:id_>")
@requiere("admin")
def editar(id_):
    """Cambia rol, nombre o estado de un usuario (admin)."""
    d = cuerpo_json()
    db = get_db()
    u = db.execute("SELECT * FROM usuarios WHERE id = ?", (id_,)).fetchone()
    if not u:
        raise ErrorAPI("Usuario no encontrado.", 404)
    rol = d.get("rol", u["rol"])
    activo = int(bool(d.get("activo", u["activo"])))
    if rol not in current_app.config["ROLES"]:
        raise ErrorAPI("Rol inválido.")
    if id_ == g.uid and (rol != "admin" or not activo):
        raise ErrorAPI("No puedes quitarte el rol de administrador ni desactivarte a ti mismo.")
    if u["rol"] == "admin" and (rol != "admin" or not activo):
        if db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1").fetchone()[0] <= 1:
            raise ErrorAPI("Debe quedar al menos un administrador activo.")
    db.execute("UPDATE usuarios SET rol = ?, activo = ?, nombre = ? WHERE id = ?",
               (rol, activo, str(d.get("nombre", u["nombre"]))[:80], id_))
    if not activo:
        db.execute("UPDATE api_tokens SET revocado = 1 WHERE usuario_id = ?", (id_,))
    registrar_auditoria(db, g.usuario, g.rol, "editar_usuario", f"usuario #{id_}",
                        f"{u['usuario']}: rol {u['rol']}→{rol}, activo {u['activo']}→{activo}")
    return jsonify(ok=True)


@bp.post("/usuarios/<int:id_>/restablecer")
@requiere("admin")
def restablecer(id_):
    """Genera una nueva clave temporal (admin)."""
    db = get_db()
    u = db.execute("SELECT usuario FROM usuarios WHERE id = ?", (id_,)).fetchone()
    if not u:
        raise ErrorAPI("Usuario no encontrado.", 404)
    temporal = auth.restablecer_clave(db, id_)
    registrar_auditoria(db, g.usuario, g.rol, "restablecer_clave", f"usuario #{id_}", u["usuario"])
    return jsonify(clave_temporal=temporal)


# ------------------------------------------------------------------ tokens
@bp.get("/tokens")
@requiere()
def mis_tokens():
    """Tokens de la API del usuario actual."""
    return jsonify(filas(get_db().execute(
        """SELECT id, nombre, prefijo, creado_en, expira_en, ultimo_uso, revocado FROM api_tokens
           WHERE usuario_id = ? ORDER BY id DESC""", (g.uid,))))


@bp.post("/tokens")
@requiere()
def nuevo_token():
    """Crea un token de la API (se muestra una vez)."""
    d = cuerpo_json()
    try:
        dias = int(d.get("dias", 90))
        assert 0 <= dias <= 365
    except (ValueError, AssertionError):
        raise ErrorAPI("La vigencia debe estar entre 0 (sin vencimiento) y 365 días.")
    db = get_db()
    token = auth.crear_token(db, g.uid, str(d.get("nombre", "")), dias)
    registrar_auditoria(db, g.usuario, g.rol, "crear_token_api", token[:10], f"vigencia {dias} días")
    return jsonify(token=token), 201


@bp.delete("/tokens/<int:id_>")
@requiere()
def revocar_token(id_):
    """Revoca un token de la API."""
    db = get_db()
    t = db.execute("SELECT usuario_id, prefijo FROM api_tokens WHERE id = ?", (id_,)).fetchone()
    if not t or (t["usuario_id"] != g.uid and g.rol != "admin"):
        raise ErrorAPI("Token no encontrado.", 404)
    db.execute("UPDATE api_tokens SET revocado = 1 WHERE id = ?", (id_,))
    registrar_auditoria(db, g.usuario, g.rol, "revocar_token_api", t["prefijo"], "")
    return jsonify(ok=True)
