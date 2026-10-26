"""
Usuarios, claves y tokens de la API.

- Las claves se guardan con hash (werkzeug: scrypt/PBKDF2 con sal). Nunca en texto plano.
- Política de claves: mínimo 10 caracteres, con letras y números.
- Tras 5 intentos fallidos la cuenta se bloquea 15 minutos.
- Un usuario creado por el administrador recibe una clave TEMPORAL y debe cambiarla
  en su primer ingreso (así el admin nunca conoce la clave definitiva del auditor).
- Los tokens de la API se muestran UNA sola vez; en la BD solo queda su hash SHA-256.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from .db import ahora

_RE_USUARIO = re.compile(r"^[a-z][a-z0-9._-]{2,31}$")
PREFIJO_TOKEN = "noc_"


class ErrorAutenticacion(ValueError):
    pass


def validar_clave(clave: str, usuario: str = "") -> None:
    if len(clave) < 10:
        raise ErrorAutenticacion("La clave debe tener al menos 10 caracteres.")
    if not re.search(r"[A-Za-z]", clave) or not re.search(r"\d", clave):
        raise ErrorAutenticacion("La clave debe combinar letras y números.")
    if usuario and usuario.lower() in clave.lower():
        raise ErrorAutenticacion("La clave no puede contener el nombre de usuario.")


def clave_temporal() -> str:
    """Clave aleatoria legible de 14 caracteres (garantiza letras y números)."""
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        clave = "".join(secrets.choice(alfabeto) for _ in range(14))
        if re.search(r"\d", clave) and re.search(r"[A-Za-z]", clave):
            return clave


def crear_usuario(conn, usuario: str, nombre: str, rol: str, clave: str, creado_por: str,
                  debe_cambiar: bool = True) -> int:
    usuario = (usuario or "").strip().lower()
    if not _RE_USUARIO.match(usuario):
        raise ErrorAutenticacion("Usuario inválido: 3-32 caracteres, minúsculas, números, punto o guion; empieza con letra.")
    if rol not in ("admin", "supervisor", "operador", "auditor"):
        raise ErrorAutenticacion("Rol inválido.")
    validar_clave(clave, usuario)
    if conn.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone():
        raise ErrorAutenticacion("Ese usuario ya existe.")
    cur = conn.execute(
        """INSERT INTO usuarios (usuario, nombre, rol, clave_hash, activo, debe_cambiar_clave, creado_por, creado_en)
           VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
        (usuario, (nombre or "").strip()[:80], rol, generate_password_hash(clave), int(debe_cambiar), creado_por, ahora()))
    conn.commit()
    return cur.lastrowid


def iniciar_sesion(conn, usuario: str, clave: str, intentos_max: int, bloqueo_min: int) -> dict:
    """Valida usuario y clave. Devuelve la fila del usuario o lanza ErrorAutenticacion."""
    u = conn.execute("SELECT * FROM usuarios WHERE usuario = ?", ((usuario or "").strip().lower(),)).fetchone()
    # Mensaje genérico: no revela si el usuario existe
    generico = ErrorAutenticacion("Usuario o clave incorrectos.")
    if u is None:
        check_password_hash(generate_password_hash("x"), clave or "")  # mismo tiempo de respuesta
        raise generico
    if not u["activo"]:
        raise ErrorAutenticacion("La cuenta está desactivada. Contacta al administrador.")
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora():
        raise ErrorAutenticacion(f"Cuenta bloqueada por intentos fallidos hasta {u['bloqueado_hasta'][11:16]}.")
    if not check_password_hash(u["clave_hash"], clave or ""):
        intentos = u["intentos_fallidos"] + 1
        bloqueo = None
        if intentos >= intentos_max:
            bloqueo = (datetime.now() + timedelta(minutes=bloqueo_min)).isoformat(timespec="seconds")
            intentos = 0
        conn.execute("UPDATE usuarios SET intentos_fallidos = ?, bloqueado_hasta = ? WHERE id = ?", (intentos, bloqueo, u["id"]))
        conn.commit()
        if bloqueo:
            raise ErrorAutenticacion(f"Demasiados intentos. Cuenta bloqueada {bloqueo_min} minutos.")
        raise generico
    conn.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = ? WHERE id = ?",
                 (ahora(), u["id"]))
    conn.commit()
    return dict(u)


def cambiar_clave(conn, usuario_id: int, actual: str, nueva: str) -> None:
    u = conn.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if not u or not check_password_hash(u["clave_hash"], actual or ""):
        raise ErrorAutenticacion("La clave actual no es correcta.")
    if actual == nueva:
        raise ErrorAutenticacion("La nueva clave debe ser distinta de la actual.")
    validar_clave(nueva, u["usuario"])
    conn.execute("UPDATE usuarios SET clave_hash = ?, debe_cambiar_clave = 0 WHERE id = ?",
                 (generate_password_hash(nueva), usuario_id))
    conn.commit()


def restablecer_clave(conn, usuario_id: int) -> str:
    """El admin genera una clave temporal nueva; el usuario debe cambiarla al entrar."""
    temporal = clave_temporal()
    conn.execute("""UPDATE usuarios SET clave_hash = ?, debe_cambiar_clave = 1, intentos_fallidos = 0,
                    bloqueado_hasta = NULL WHERE id = ?""", (generate_password_hash(temporal), usuario_id))
    conn.commit()
    return temporal


# ------------------------------------------------------------------ tokens
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_token(conn, usuario_id: int, nombre: str, dias: int) -> str:
    token = PREFIJO_TOKEN + secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(days=dias)).isoformat(timespec="seconds") if dias else None
    conn.execute(
        "INSERT INTO api_tokens (usuario_id, nombre, prefijo, token_hash, creado_en, expira_en) VALUES (?, ?, ?, ?, ?, ?)",
        (usuario_id, nombre.strip()[:60] or "token", token[:10], _hash_token(token), ahora(), expira))
    conn.commit()
    return token


def usuario_por_token(conn, token: str):
    if not token or not token.startswith(PREFIJO_TOKEN):
        return None
    fila = conn.execute(
        """SELECT u.*, t.id AS token_id, t.expira_en FROM api_tokens t JOIN usuarios u ON u.id = t.usuario_id
           WHERE t.token_hash = ? AND t.revocado = 0 AND u.activo = 1""", (_hash_token(token),)).fetchone()
    if not fila or (fila["expira_en"] and fila["expira_en"] < ahora()):
        return None
    conn.execute("UPDATE api_tokens SET ultimo_uso = ? WHERE id = ?", (ahora(), fila["token_id"]))
    conn.commit()
    return fila
