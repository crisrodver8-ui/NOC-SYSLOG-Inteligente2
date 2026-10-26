"""
Parser de mensajes Syslog.

Soporta:
  * RFC 5424  ->  <PRI>1 TIMESTAMP HOST APP PROCID MSGID [SD] MENSAJE
  * RFC 3164  ->  <PRI>Mmm dd hh:mm:ss HOST TAG: MENSAJE   (BSD, el más común)
  * Cisco IOS ->  <PRI>seq: *Mmm dd hh:mm:ss.mmm: %FAC-SEV-MNEMONIC: texto
  * Fortinet  ->  <PRI>date=AAAA-MM-DD time=hh:mm:ss devname="X" level="..." ...
  * Huawei    ->  <PRI>Mmm dd AAAA hh:mm:ss HOST %%01MOD/SEV/INFO(l)[n]: texto

El PRI codifica facility y severidad:  PRI = facility * 8 + severidad
Ejemplo: <189>  ->  189 // 8 = 23 (local7)   y   189 % 8 = 5 (Notice)

IMPORTANTE: el contenido del mensaje es un DATO NO CONFIABLE. El parser solo
lo extrae y clasifica; nunca lo interpreta como una instrucción.
"""
import re
from dataclasses import dataclass
from datetime import datetime

SEVERIDADES = {
    0: "Emergency", 1: "Alert", 2: "Critical", 3: "Error",
    4: "Warning", 5: "Notice", 6: "Informational", 7: "Debug",
}

# Códigos de facility según RFC 5424 (posición = número)
FACILITIES = [
    "kern", "user", "mail", "daemon", "auth", "syslog", "lpr", "news",
    "uucp", "cron", "authpriv", "ftp", "ntp", "security", "console", "clock",
    "local0", "local1", "local2", "local3", "local4", "local5", "local6", "local7",
]

# Si el mensaje no trae PRI, RFC 3164 indica asumir <13> = user.notice
PRI_POR_DEFECTO = 13

_MESES = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

_RE_PRI = re.compile(r"^<(\d{1,3})>")
_RE_5424 = re.compile(r"^1 (\S+) (\S+) (\S+) (\S+) (\S+) (-|(?:\[.*?\])+)\s?(.*)$", re.S)
_RE_FECHA_BSD = r"([A-Z][a-z]{2})\s+(\d{1,2})\s+(?:(\d{4})\s+)?(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?"
_RE_CISCO = re.compile(
    r"^(?:\d+:\s+)?(?:(\S+):\s+)?[*.]?" + _RE_FECHA_BSD + r"(?:\s+[A-Z]{2,5})?:\s+(%[A-Z0-9_]+-[0-7]-[A-Z0-9_]+):?\s*(.*)$",
    re.S,
)
_RE_3164 = re.compile(r"^" + _RE_FECHA_BSD + r"\s+(\S+)\s+(.*)$", re.S)
_RE_TAG = re.compile(r"^([^\s:\[]{1,64}(?:\[[^\]]*\])?(?:\([a-z]\))?(?:\[\d+\])?):\s*(.*)$", re.S)
_RE_KV = re.compile(r'(\w+)=("([^"]*)"|\S+)')

_RE_MARCA_CISCO = re.compile(r"%[A-Z0-9_]+-[0-7]-[A-Z0-9_]+")


@dataclass
class MensajeSyslog:
    facility: int
    severidad: int
    fecha_evento: str | None   # ISO o None si no se pudo leer
    hostname: str | None
    app: str | None
    mensaje: str
    crudo: str
    formato: str               # rfc5424 | rfc3164 | cisco | fortinet | sin_formato
    marca_detectada: str | None

    @property
    def facility_nombre(self) -> str:
        return FACILITIES[self.facility] if 0 <= self.facility < len(FACILITIES) else f"facility{self.facility}"

    @property
    def severidad_nombre(self) -> str:
        return SEVERIDADES[self.severidad]


def detectar_marca(texto: str) -> str | None:
    """Pista de fabricante a partir del contenido (el inventario tiene prioridad)."""
    if "%%" in texto:
        return "Huawei"
    if "devname=" in texto or "logid=" in texto:
        return "Fortinet"
    if _RE_MARCA_CISCO.search(texto):
        return "Cisco"
    return None


def _fecha_bsd(mes, dia, anio, hh, mm, ss) -> str | None:
    """Convierte 'Oct 9 10:00:00' en ISO. Si no trae año se usa el actual."""
    try:
        return datetime(int(anio or datetime.now().year), _MESES[mes], int(dia),
                        int(hh), int(mm), int(ss)).isoformat(timespec="seconds")
    except (KeyError, ValueError):
        return None


def _fecha_iso(texto: str) -> str | None:
    """ISO 8601. Si trae zona horaria (ej. Z = UTC) se convierte a la hora local del colector."""
    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone().replace(tzinfo=None)
    return fecha.isoformat(timespec="seconds")


def _separar_tag(contenido: str) -> tuple[str | None, str]:
    m = _RE_TAG.match(contenido)
    if m:
        # Quita contadores variables del tag (ej. Huawei "...(l)[3]") para que
        # la deduplicación reconozca mensajes iguales.
        return re.sub(r"\[\d+\]$", "", m.group(1)), m.group(2).strip()
    return None, contenido.strip()


def parsear(crudo: str) -> MensajeSyslog:
    """Analiza un mensaje Syslog y devuelve sus partes. Nunca lanza excepción."""
    texto = crudo.strip()

    # 1) PRI -> facility y severidad
    m = _RE_PRI.match(texto)
    pri = PRI_POR_DEFECTO
    if m and int(m.group(1)) <= 191:
        pri = int(m.group(1))
        resto = texto[m.end():]
    else:
        resto = texto
    facility, severidad = divmod(pri, 8)
    marca = detectar_marca(resto)

    def armar(fecha, host, app, mensaje, formato):
        return MensajeSyslog(facility, severidad, fecha, host, app, mensaje, crudo, formato, marca)

    # 2) RFC 5424
    m = _RE_5424.match(resto)
    if m:
        ts, host, app, _procid, _msgid, _sd, msg = m.groups()
        return armar(_fecha_iso(ts) if ts != "-" else None,
                     None if host == "-" else host,
                     None if app == "-" else app,
                     msg.lstrip("\ufeff").strip(), "rfc5424")

    # 3) Fortinet (formato clave=valor)
    if "devname=" in resto or resto.startswith("date="):
        # findall devuelve (clave, valor_completo, valor_sin_comillas)
        kv = {k: (interno if v.startswith('"') else v) for k, v, interno in _RE_KV.findall(resto)}
        fecha = _fecha_iso(f"{kv.get('date', '')}T{kv.get('time', '')}") if "date" in kv else None
        app = "/".join(x for x in (kv.get("type"), kv.get("subtype")) if x) or "fortios"
        # El mensaje se guarda sin los campos de fecha (date/time/eventtime/tz): así dos
        # eventos iguales en momentos distintos se reconocen como duplicados.
        mensaje = re.sub(r'\b(date|time|eventtime|tz)=("[^"]*"|\S+)\s*', "", resto).strip()
        return armar(fecha, kv.get("devname"), app, mensaje, "fortinet")

    # 4) Cisco IOS
    m = _RE_CISCO.match(resto)
    if m:
        host, mes, dia, anio, hh, mm, ss, mnemonico, msg = m.groups()
        return armar(_fecha_bsd(mes, dia, anio, hh, mm, ss), host, mnemonico.lstrip("%"),
                     f"{mnemonico}: {msg.strip()}", "cisco")

    # 5) RFC 3164 (incluye el formato Huawei, que agrega el año)
    m = _RE_3164.match(resto)
    if m:
        mes, dia, anio, hh, mm, ss, host, contenido = m.groups()
        app, msg = _separar_tag(contenido)
        return armar(_fecha_bsd(mes, dia, anio, hh, mm, ss), host, app, msg or contenido, "rfc3164")

    # 6) Sin formato reconocible: se guarda tal cual
    return armar(None, None, None, resto, "sin_formato")
