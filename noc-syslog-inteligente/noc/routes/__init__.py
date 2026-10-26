"""
Rutas de la API REST y utilidades comunes (autenticación, roles y errores).

Dos formas de autenticarse:
  1. Sesión del navegador (cookie firmada) después de iniciar sesión.
  2. Token de la API:  Authorization: Bearer noc_xxxxx   (integraciones externas)

Roles:
  admin       gestiona usuarios y configuración + todo lo del supervisor.
  supervisor  aprueba o rechaza acciones, elimina equipos.
  operador    inventario, eventos, incidentes, consola; PROPONE y ejecuta lo aprobado.
  auditor     solo lectura + auditoría + verificación de integridad.
"""
from functools import wraps

from flask import g, jsonify, request, session

from ..autenticacion import usuario_por_token
from ..db import get_db

# Qué roles "heredan" permisos de otro: el admin puede todo lo del supervisor, etc.
JERARQUIA = {
    "admin": {"admin", "supervisor", "operador", "auditor"},
    "supervisor": {"supervisor", "operador"},
    "operador": {"operador"},
    "auditor": {"auditor"},
}
METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}


class ErrorAPI(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


def _usuario_actual():
    """Identifica al usuario por token Bearer o por la sesión. Devuelve la fila o None."""
    db = get_db()
    cabecera = request.headers.get("Authorization", "")
    if cabecera.startswith("Bearer "):
        fila = usuario_por_token(db, cabecera[7:].strip())
        if fila:
            g.via = "token"
        return fila
    uid = session.get("uid")
    if uid is None:
        return None
    fila = db.execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1", (uid,)).fetchone()
    if fila is None or session.get("version_clave") != fila["clave_hash"][-12:]:
        session.clear()  # la clave cambió o el usuario fue desactivado: sesión inválida
        return None
    # Protección CSRF: las escrituras desde el navegador deben traer la cabecera X-NOC
    # (un sitio externo no puede agregarla sin permiso CORS).
    if request.method in METODOS_ESCRITURA and request.headers.get("X-NOC") != "1":
        raise ErrorAPI("Solicitud rechazada (falta la cabecera de protección CSRF).", 403)
    g.via = "sesion"
    return fila


def requiere(*roles, permitir_cambio_pendiente: bool = False):
    """Decorador: exige usuario autenticado y, si se indican, alguno de los roles."""
    def decorador(fn):
        @wraps(fn)
        def envoltura(*args, **kwargs):
            u = _usuario_actual()
            if u is None:
                raise ErrorAPI("Debes iniciar sesión o usar un token válido.", 401)
            if u["debe_cambiar_clave"] and not permitir_cambio_pendiente and getattr(g, "via", "") == "sesion":
                raise ErrorAPI("Debes cambiar tu clave temporal antes de continuar.", 403)
            if roles and not (JERARQUIA[u["rol"]] & set(roles)):
                raise ErrorAPI(f"El rol '{u['rol']}' no puede realizar esta acción.", 403)
            g.usuario, g.rol, g.uid = u["usuario"], u["rol"], u["id"]
            return fn(*args, **kwargs)
        return envoltura
    return decorador


def cuerpo_json() -> dict:
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ErrorAPI("Se esperaba un cuerpo JSON.")
    return datos


def registrar_rutas(app):
    from . import acciones, dispositivos, eventos, herramientas, incidentes, usuarios

    for modulo in (usuarios, dispositivos, eventos, incidentes, acciones, herramientas):
        app.register_blueprint(modulo.bp, url_prefix="/api")

    @app.errorhandler(ErrorAPI)
    def _error_api(e):
        return jsonify(error=e.mensaje), e.codigo

    @app.errorhandler(413)
    def _muy_grande(_e):
        return jsonify(error="Archivo demasiado grande (máximo 2 MB)."), 413

    @app.errorhandler(404)
    def _no_encontrado(_e):
        return jsonify(error="Recurso no encontrado."), 404
