"""
Generador de configuraciones Syslog comentadas para Cisco, Fortinet y Huawei.

Los valores que ingresa el usuario se VALIDAN antes de ponerlos en la
plantilla (IP, puerto, interfaz), para que nadie pueda inyectar comandos
adicionales a través del formulario.
"""
import ipaddress
import re

NIVELES = {  # severidad -> nombre que usa cada fabricante
    "Cisco":    ["emergencies", "alerts", "critical", "errors", "warnings", "notifications", "informational", "debugging"],
    "Fortinet": ["emergency", "alert", "critical", "error", "warning", "notification", "information", "debug"],
    "Huawei":   ["emergencies", "alert", "critical", "error", "warning", "notification", "informational", "debugging"],
}
_RE_INTERFAZ = re.compile(r"^[A-Za-z][A-Za-z0-9/.\-]{0,40}$")
_RE_ZONA = re.compile(r"^[A-Za-z]{2,6}$")


class ErrorValidacion(ValueError):
    pass


def _validar(datos: dict) -> dict:
    marca = datos.get("marca")
    if marca not in NIVELES:
        raise ErrorValidacion("Marca no soportada (Cisco, Fortinet o Huawei).")
    try:
        servidor = str(ipaddress.IPv4Address(str(datos.get("servidor", "")).strip()))
        ntp = str(ipaddress.IPv4Address(str(datos.get("ntp", "")).strip()))
    except ipaddress.AddressValueError:
        raise ErrorValidacion("La IP del servidor Syslog y la del NTP deben ser IPv4 válidas.")
    try:
        puerto = int(datos.get("puerto", 514))
        nivel = int(datos.get("nivel", 6))
        facility = int(datos.get("facility", 7))
    except (TypeError, ValueError):
        raise ErrorValidacion("Puerto, nivel y facility deben ser números.")
    if not 1 <= puerto <= 65535:
        raise ErrorValidacion("Puerto fuera de rango (1-65535).")
    if not 0 <= nivel <= 7 or not 0 <= facility <= 7:
        raise ErrorValidacion("Nivel 0-7 y facility local0-local7.")
    protocolo = datos.get("protocolo", "udp")
    if protocolo not in ("udp", "tcp"):
        raise ErrorValidacion("Protocolo debe ser udp o tcp.")
    interfaz = str(datos.get("interfaz", "")).strip()
    if interfaz and not _RE_INTERFAZ.match(interfaz):
        raise ErrorValidacion("Nombre de interfaz inválido.")
    zona = str(datos.get("zona", "COT")).strip() or "COT"
    if not _RE_ZONA.match(zona):
        raise ErrorValidacion("Zona horaria inválida (ej. COT).")
    return dict(marca=marca, servidor=servidor, ntp=ntp, puerto=puerto, nivel=nivel,
                facility=facility, protocolo=protocolo, interfaz=interfaz, zona=zona.upper())


def _cisco(c: dict) -> str:
    nivel = NIVELES["Cisco"][c["nivel"]]
    origen = f" logging source-interface {c['interfaz']}\n" if c["interfaz"] else \
             " ! (Opcional) logging source-interface Loopback0  -> fija la IP de origen\n"
    return f"""! =====================================================================
! Configuración Syslog - Cisco IOS / IOS-XE
! Generada por NOC Syslog Inteligente. Revisar antes de aplicar.
! =====================================================================
configure terminal
 ! --- 1. Hora sincronizada: sin NTP las marcas de tiempo no son confiables
 ntp server {c['ntp']}
 clock timezone {c['zona']} -5 0
 ! --- 2. Fecha, hora y número de secuencia en cada mensaje
 service timestamps log datetime msec localtime show-timezone
 service sequence-numbers
 ! --- 3. Servidor Syslog del NOC (colector central)
 logging host {c['servidor']} transport {c['protocolo']} port {c['puerto']}
 ! --- 4. Enviar severidades 0 a {c['nivel']} ({nivel})
 logging trap {nivel}
 ! --- 5. Facility con la que se etiquetan los mensajes
 logging facility local{c['facility']}
 ! --- 6. IP de origen fija = la que se registra en la lista permitida del NOC
{origen} ! --- 7. Registrar accesos exitosos y fallidos (detecta fuerza bruta)
 !     login block-for es necesario en IOS para que se registren los intentos
 login block-for 60 attempts 5 within 60
 login on-failure log
 login on-success log
 ! --- 8. Registrar cada comando de configuración (quién cambió qué)
 archive
  log config
   logging enable
   notify syslog contenttype plaintext
   hidekeys
 exit
 exit
 logging on
end
! --- 9. Guardar la configuración
write memory
!
! Verificación:
!   show logging
!   show ntp status
!   show archive log config all
"""


def _fortinet(c: dict) -> str:
    nivel = NIVELES["Fortinet"][c["nivel"]]
    modo = "udp" if c["protocolo"] == "udp" else "reliable"
    origen = f'    set source-ip "{c["interfaz"]}"\n' if c["interfaz"] and re.match(r"^\d", c["interfaz"]) else ""
    return f"""# =====================================================================
# Configuración Syslog - Fortinet FortiGate (FortiOS 7.x)
# Generada por NOC Syslog Inteligente. Las líneas con # son comentarios:
# quítalas si pegas la configuración directamente en la CLI.
# =====================================================================

# --- 1. Hora sincronizada con NTP
config system ntp
    set ntpsync enable
    set type custom
    config ntpserver
        edit 1
            set server "{c['ntp']}"
        next
    end
end

# --- 2. Servidor Syslog del NOC
config log syslogd setting
    set status enable
    set server "{c['servidor']}"
    set port {c['puerto']}
    # udp = estándar, reliable = TCP (RFC 6587)
    set mode {modo}
    set facility local{c['facility']}
{origen}    set format default
end

# --- 3. Qué se envía: severidad {c['nivel']} ({nivel}) o más grave + eventos del sistema
config log syslogd filter
    set severity {nivel}
    set forward-traffic enable
    set local-traffic enable
end

# --- 4. Registrar eventos administrativos (logins y cambios de configuración)
config log eventfilter
    set event enable
    set system enable
end

# Verificación:
#   get log syslogd setting
#   diagnose log test
#   execute log filter category event
"""


def _huawei(c: dict) -> str:
    nivel = NIVELES["Huawei"][c["nivel"]]
    origen = f" info-center loghost source {c['interfaz']}\n" if c["interfaz"] else \
             " # (Opcional) info-center loghost source LoopBack0  -> fija la IP de origen\n"
    puerto = f" port {c['puerto']}" if c["puerto"] != 514 else ""
    return f"""# =====================================================================
# Configuración Syslog - Huawei VRP (switches S / routers AR)
# Generada por NOC Syslog Inteligente. Las líneas con # son comentarios.
# =====================================================================
system-view
 # --- 1. Hora sincronizada con NTP
 ntp-service unicast-server {c['ntp']}
 clock timezone {c['zona']} minus 05:00:00
 # --- 2. Activar el centro de información (sistema de logs)
 info-center enable
 # --- 3. Servidor Syslog del NOC con su facility
 info-center loghost {c['servidor']}{puerto} facility local{c['facility']}
 # --- 4. IP de origen fija = la registrada en la lista permitida del NOC
{origen} # --- 5. Enviar severidad {c['nivel']} ({nivel}) o más grave al canal loghost
 info-center source default channel loghost log level {nivel}
 # --- 6. Fecha completa en cada mensaje
 info-center timestamp log date
 quit
# --- 7. Guardar la configuración
save
#
# Verificación:
#   display info-center
#   display ntp-service status
#   display logbuffer
"""


def generar(datos: dict) -> str:
    c = _validar(datos)
    return {"Cisco": _cisco, "Fortinet": _fortinet, "Huawei": _huawei}[c["marca"]](c)
