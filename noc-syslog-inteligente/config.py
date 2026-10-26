"""
Configuración central de la aplicación.

Todos los valores se leen de variables de entorno (archivo .env) para que
ningún secreto (clave de sesión, token de Telegram, claves SSH) quede
escrito en el código fuente ni se suba a GitHub.
"""
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _entero(nombre: str, defecto: int) -> int:
    """Lee una variable de entorno numérica; si no existe o es inválida usa el valor por defecto."""
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


def _clave_sesion() -> str:
    """
    Clave para firmar las cookies de sesión.
    1) Si está en .env (FLASK_SECRET_KEY) se usa esa.
    2) Si no, se genera una aleatoria UNA vez y se guarda en data/secret_key
       (carpeta excluida de GitHub), para que las sesiones sobrevivan a un reinicio.
    """
    if os.getenv("FLASK_SECRET_KEY"):
        return os.environ["FLASK_SECRET_KEY"]
    ruta = os.path.join(BASE_DIR, "data", "secret_key")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    if not os.path.exists(ruta):
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
    with open(ruta, encoding="utf-8") as f:
        return f.read().strip()


class Config:
    VERSION = "1.0.0"

    # --- Sesiones (login) ---
    SECRET_KEY = _clave_sesion()
    SESSION_COOKIE_HTTPONLY = True          # JavaScript no puede leer la cookie
    SESSION_COOKIE_SAMESITE = "Strict"      # no se envía desde otros sitios (anti-CSRF)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_entero("SESION_HORAS", 8))
    INTENTOS_LOGIN_MAX = 5                  # bloqueo tras 5 fallos...
    BLOQUEO_MINUTOS = 15                    # ...durante 15 minutos

    WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT = _entero("WEB_PORT", 8080)

    DB_PATH = os.path.join(BASE_DIR, os.getenv("NOC_DB_PATH", "data/noc.db"))
    RESPALDOS_DIR = os.path.join(BASE_DIR, os.getenv("RESPALDOS_DIR", "respaldos"))

    # --- Receptor Syslog ---
    SYSLOG_LISTENER = os.getenv("SYSLOG_LISTENER", "1") == "1"
    SYSLOG_HOST = os.getenv("SYSLOG_HOST", "0.0.0.0")
    SYSLOG_PORT = _entero("SYSLOG_PORT", 5514)

    # --- Políticas de defensa ---
    DEDUP_VENTANA_S = _entero("DEDUP_VENTANA_S", 60)
    LIMITE_MENSAJES_MIN = _entero("LIMITE_MENSAJES_MIN", 120)
    HORARIO_INICIO = _entero("HORARIO_INICIO", 7)
    HORARIO_FIN = _entero("HORARIO_FIN", 19)
    SEVERIDAD_AUTO_INCIDENTE = _entero("SEVERIDAD_AUTO_INCIDENTE", 2)
    INTENTOS_FUERZA_BRUTA = 4
    DESFASE_MAX_S = _entero("DESFASE_MAX_S", 300)       # diferencia máxima hora equipo vs. colector
    RAFAGA_CAMBIOS = _entero("RAFAGA_CAMBIOS", 5)        # cambios de config en 60 s = ritmo de máquina
    VENTANA_CAMBIO_AUTORIZADO_MIN = 30                   # un cambio necesita acción aprobada reciente

    # --- Hora del servidor (NTP) ---
    NTP_SERVIDOR = os.getenv("NTP_SERVIDOR", "pool.ntp.org")
    NTP_DESFASE_MAX_MS = _entero("NTP_DESFASE_MAX_MS", 2000)

    # --- Telegram (el token SOLO va en .env) ---
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_SEVERIDAD_MAX = _entero("TELEGRAM_SEVERIDAD_MAX", 2)
    TELEGRAM_LIMITE_MIN = _entero("TELEGRAM_LIMITE_MIN", 20)

    # --- Gestor SSH / consola (las claves SOLO van en .env) ---
    SSH_USUARIO = os.getenv("SSH_USUARIO", "")
    SSH_CLAVE = os.getenv("SSH_CLAVE", "")
    SSH_TIMEOUT_S = _entero("SSH_TIMEOUT_S", 8)
    # Hosts a los que el backend puede conectarse por telnet de consola (GNS3)
    CONSOLA_HOSTS_PERMITIDOS = [h.strip() for h in os.getenv("CONSOLA_HOSTS_PERMITIDOS", "127.0.0.1,localhost").split(",") if h.strip()]

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # Roles y lo que puede hacer cada uno (ver docs/manual_tecnico.md)
    ROLES = ("admin", "supervisor", "operador", "auditor")
