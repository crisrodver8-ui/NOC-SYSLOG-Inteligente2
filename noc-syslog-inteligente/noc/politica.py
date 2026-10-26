"""
Política de defensa frente a acciones de agentes de IA (y ataques en general).

Cada evento se revisa con reglas EXPLÍCITAS y deterministas. El resultado son
"banderas" que se guardan con el evento y que marcan si es sospechoso.

Banderas posibles:
  fuente_no_autorizada  La IP de origen no está en la lista permitida del inventario.
  posible_inyeccion     El texto intenta dar órdenes a una IA o contiene comandos peligrosos.
  fallo_autenticacion   Login fallido.
  fuerza_bruta          Varios fallos de login desde el mismo equipo en pocos minutos.
  acceso                Login exitoso.
  cambio_config         Se modificó la configuración del equipo.
  fuera_de_horario      Acceso o cambio de configuración fuera del horario laboral.
  cuenta_servicio       Una cuenta de servicio / agente automatizado hizo un acceso o cambio.
  tormenta              Se superó el límite de mensajes por minuto de una fuente.

Nuevas en v1.0.0 (módulo mejorado):
  ofuscacion            Caracteres invisibles, texto bidireccional o bloques base64/hex largos:
                        técnicas para esconder instrucciones a una IA.
  hora_desfasada        La hora que reporta el equipo difiere de la del colector más de lo
                        permitido (NTP mal configurado o reloj manipulado).
  rafaga_cambios        Varios cambios de configuración en un minuto: ritmo de máquina, no humano.
  cambio_no_autorizado  Cambio de configuración sin una acción APROBADA reciente en el NOC
                        para ese equipo (correlación Syslog + flujo de aprobación).

Cada evento recibe además un puntaje de RIESGO de 0 a 100.

Regla de oro: el texto del log se ANALIZA como dato. Nunca se ejecuta ni se
envía como instrucción a una IA.
"""
import hashlib
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime

# --- Patrones de inyección de instrucciones (prompt injection) y comandos peligrosos ---
PATRONES_INYECCION = [re.compile(p, re.I) for p in (
    r"ignor(e|a|ar)\s+(all\s+|todas?\s+)?(the\s+|las\s+|los\s+)?(previous|prior|anteriores|above)?\s*(instructions|instrucciones|reglas|rules)",
    r"(olvida|forget)\s+(todo|everything|tus|your)",
    r"system\s*prompt|prompt\s+del\s+sistema",
    r"(you\s+are\s+now|ahora\s+eres|act[uú]a\s+como)\b",
    r"\b(as an ai|como (una )?ia|dear (ai|assistant|agent)|querid[oa] (ia|asistente|agente))\b",
    r"(ejecuta|execute|run)\s+(el\s+)?(comando|command)",
    r"\bwrite\s+erase\b|\berase\s+startup|\breload\b\s*(in|now)?|\bformat\s+flash",
    r"execute\s+(factoryreset|formatlogdisk|reboot)",
    r"\brm\s+-rf\b|curl\s+[^|]+\|\s*(ba)?sh|wget\s+[^|]+\|\s*(ba)?sh",
    r"<script\b|javascript:",
    r"(api[_-]?key|token|password|contraseña)\s*[:=]",
)]

RE_FALLO_AUTH = re.compile(
    r"LOGIN_FAILED|SSH_FAIL|login failed|authentication fail|failed password|Admin login failed|"
    r"Failed to login|invalid user", re.I)
RE_ACCESO_OK = re.compile(
    r"LOGIN_SUCCESS|Login Success|Accepted password|logged in successfully|Admin login successful|"
    r"succeeded in logging in", re.I)
RE_CAMBIO_CONFIG = re.compile(
    r"CONFIG_I|CFGLOG_LOGGEDCMD|Configured from|CFG_CHANGE|Configuration changed|cfgattr=|"
    r"CMDRECORD.*Command=\"(?!display)|config change|SAVE\(s\)", re.I)
RE_CUENTA_SERVICIO = re.compile(
    r"\b(svc[-_.]\w+|srv[-_.]\w+|ai[-_]?agent\w*|agente[-_]ia\w*|bot[-_.]\w+|automation\w*|llm[-_]\w+)\b", re.I)

# Ofuscación: caracteres invisibles / de control bidireccional y bloques codificados largos
RE_INVISIBLES = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
RE_CODIFICADO = re.compile(r"(?:[A-Za-z0-9+/]{40,}={0,2})|(?:(?:\\x[0-9a-fA-F]{2}){8,})|(?:(?:%[0-9a-fA-F]{2}){8,})")

# Banderas que, por sí solas, vuelven sospechoso un evento
BANDERAS_SOSPECHOSAS = {
    "fuente_no_autorizada", "posible_inyeccion", "fuerza_bruta", "fuera_de_horario",
    "cuenta_servicio", "tormenta", "ofuscacion", "hora_desfasada", "rafaga_cambios",
    "cambio_no_autorizado",
}

# Peso de cada bandera en el puntaje de riesgo (0-100)
PESOS_RIESGO = {
    "posible_inyeccion": 40, "cambio_no_autorizado": 35, "fuente_no_autorizada": 30,
    "fuerza_bruta": 30, "rafaga_cambios": 30, "ofuscacion": 25, "cuenta_servicio": 20,
    "fuera_de_horario": 15, "hora_desfasada": 15, "tormenta": 15, "cambio_config": 10,
    "fallo_autenticacion": 5, "acceso": 2,
}


def limpiar_invisibles(texto: str) -> str:
    """Quita caracteres invisibles para que "ig\u200bnore" se detecte como "ignore"."""
    return RE_INVISIBLES.sub("", texto)


def analizar_texto(mensaje: str, fecha: datetime, horario_inicio: int, horario_fin: int) -> list[str]:
    """Aplica las reglas de contenido. Devuelve la lista de banderas."""
    banderas = []
    limpio = limpiar_invisibles(mensaje)
    if limpio != mensaje or RE_CODIFICADO.search(mensaje):
        banderas.append("ofuscacion")
    if any(p.search(limpio) for p in PATRONES_INYECCION):
        banderas.append("posible_inyeccion")
    if RE_FALLO_AUTH.search(limpio):
        banderas.append("fallo_autenticacion")
    elif RE_ACCESO_OK.search(limpio):
        banderas.append("acceso")
    if RE_CAMBIO_CONFIG.search(limpio):
        banderas.append("cambio_config")

    relevante = {"acceso", "cambio_config"} & set(banderas)
    if relevante:
        laboral = horario_inicio <= fecha.hour < horario_fin and fecha.weekday() < 5
        if not laboral:
            banderas.append("fuera_de_horario")
        if RE_CUENTA_SERVICIO.search(limpio):
            banderas.append("cuenta_servicio")
    elif "fallo_autenticacion" in banderas and RE_CUENTA_SERVICIO.search(limpio):
        banderas.append("cuenta_servicio")
    return banderas


def es_sospechoso(banderas: list[str]) -> bool:
    return bool(BANDERAS_SOSPECHOSAS & set(banderas))


def puntaje_riesgo(banderas: list[str], severidad: int) -> int:
    """Riesgo 0-100: suma de pesos de las banderas + un aporte por severidad (0 suma 21, 7 suma 0)."""
    base = sum(PESOS_RIESGO.get(b, 0) for b in set(banderas))
    return min(100, base + (7 - severidad) * 3)


def huella(ip: str, severidad: int, app: str | None, mensaje: str) -> str:
    """Hash usado para deduplicar: mismo origen + severidad + contenido = mismo evento."""
    base = f"{ip}|{severidad}|{app or ''}|{mensaje.strip()}"
    return hashlib.sha256(base.encode("utf-8", "replace")).hexdigest()[:32]


class LimitadorFrecuencia:
    """
    Control de tormentas de eventos: ventana deslizante de 60 s por IP de origen.
    Si una fuente supera el límite, sus mensajes se descartan hasta que baje.
    """

    def __init__(self, limite_por_minuto: int):
        self.limite = limite_por_minuto
        self._ventanas: dict[str, deque] = defaultdict(deque)
        self._ultima_alerta: dict[str, float] = {}
        self.descartados: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()   # el receptor UDP y la web lo usan a la vez

    def permitir(self, ip: str, ahora: float | None = None) -> bool:
        ahora = time.monotonic() if ahora is None else ahora
        with self._lock:
            ventana = self._ventanas[ip]
            while ventana and ahora - ventana[0] > 60:
                ventana.popleft()
            if len(ventana) >= self.limite:
                self.descartados[ip] += 1
                return False
            ventana.append(ahora)
            return True

    def debe_alertar(self, ip: str, ahora: float | None = None) -> bool:
        """Solo una alerta de tormenta por IP cada 60 s (para no crear otra tormenta)."""
        ahora = time.monotonic() if ahora is None else ahora
        with self._lock:
            if ahora - self._ultima_alerta.get(ip, -1e9) >= 60:
                self._ultima_alerta[ip] = ahora
                return True
            return False

    def total_descartados(self) -> int:
        return sum(self.descartados.values())
