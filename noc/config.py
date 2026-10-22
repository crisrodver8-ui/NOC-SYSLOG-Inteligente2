"""
Configuración central de la aplicación.

Todos los valores se leen de variables de entorno (archivo .env) para que
ningún secreto quede escrito en el código fuente.
"""
import os
import secrets

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _entero(nombre: str, defecto: int) -> int:
    """Lee una variable de entorno numérica; si no existe o es inválida usa el valor por defecto."""
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


class Config:
    VERSION = "0.2.0"

    # Si no hay clave en .env se genera una aleatoria en cada arranque (nunca fija en el código)
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)

    WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT = _entero("WEB_PORT", 8080)

    DB_PATH = os.path.join(BASE_DIR, os.getenv("NOC_DB_PATH", "data/noc.db"))

    # Receptor Syslog
    SYSLOG_LISTENER = os.getenv("SYSLOG_LISTENER", "1") == "1"
    SYSLOG_HOST = os.getenv("SYSLOG_HOST", "0.0.0.0")
    SYSLOG_PORT = _entero("SYSLOG_PORT", 5514)

    # Políticas de defensa
    DEDUP_VENTANA_S = _entero("DEDUP_VENTANA_S", 60)            # deduplicación
    LIMITE_MENSAJES_MIN = _entero("LIMITE_MENSAJES_MIN", 120)   # control de tormentas por IP
    HORARIO_INICIO = _entero("HORARIO_INICIO", 7)               # horario laboral
    HORARIO_FIN = _entero("HORARIO_FIN", 19)
    SEVERIDAD_AUTO_INCIDENTE = _entero("SEVERIDAD_AUTO_INCIDENTE", 2)  # 0..N crea incidente
    INTENTOS_FUERZA_BRUTA = 4                                   # fallos de login en 5 min

    # Tamaño máximo de archivo importado (2 MB)
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024

    # Usuarios simulados del MVP y su rol (en v1.0.0 se reemplaza por login real)
    USUARIOS = {
        "operador1": "operador",
        "operador2": "operador",
        "supervisor1": "supervisor",
        "auditor1": "auditor",
    }
