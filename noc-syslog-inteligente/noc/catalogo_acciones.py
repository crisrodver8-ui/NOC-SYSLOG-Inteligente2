"""
Catálogo cerrado de acciones de respuesta.

Una acción NUNCA se arma con texto copiado de un log: solo se elige un tipo
de este catálogo y un parámetro validado (IP o nombre de usuario). El comando
final sale de una plantilla fija por fabricante.
"""
import ipaddress
import re

CATALOGO = {
    "observar": {
        "nombre": "Mantener en observación (sin cambios)",
        "parametro": None,
        "plantillas": {"*": "! Sin cambios en el equipo. Seguimiento desde el NOC."},
    },
    "bloquear_ip": {
        "nombre": "Bloquear IP de origen",
        "parametro": "ip",
        "plantillas": {
            "Cisco": "ip access-list extended NOC-CUARENTENA\n 10 deny ip host {p} any log\n 20 permit ip any any",
            "Fortinet": 'config firewall address\n edit "NOC-BLOQ-{p}"\n  set subnet {p} 255.255.255.255\n next\nend',
            "Huawei": "acl number 3999\n rule 5 deny ip source {p} 0",
        },
    },
    "deshabilitar_cuenta": {
        "nombre": "Deshabilitar cuenta de usuario / servicio",
        "parametro": "usuario",
        "plantillas": {
            "Cisco": "no username {p}",
            "Fortinet": "config system admin\n delete {p}\nend",
            "Huawei": "aaa\n local-user {p} state block",
        },
    },
    "restaurar_config": {
        "nombre": "Restaurar la última configuración respaldada",
        "parametro": None,
        "modo": "exec",   # se ejecuta fuera del modo configuración
        "plantillas": {
            "Cisco": "configure replace flash:noc-respaldo.cfg list",
            "Fortinet": "execute restore config flash noc-respaldo",
            "Huawei": "startup saved-configuration noc-respaldo.cfg",
        },
    },
    "escalar": {
        "nombre": "Escalar al fabricante / segundo nivel",
        "parametro": None,
        "plantillas": {"*": "! Sin cambios en el equipo. Se escala el caso."},
    },
}

_RE_USUARIO = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


class AccionInvalida(ValueError):
    pass


def construir_comando(tipo: str, marca: str, parametro: str | None) -> str:
    """Paso de VALIDACIÓN del flujo seguro: si algo no cuadra, se rechaza aquí."""
    if tipo not in CATALOGO:
        raise AccionInvalida("Tipo de acción fuera del catálogo permitido.")
    accion = CATALOGO[tipo]
    p = (parametro or "").strip()
    if accion["parametro"] == "ip":
        try:
            p = str(ipaddress.ip_address(p))
        except ValueError:
            raise AccionInvalida("La acción requiere una IP válida.")
    elif accion["parametro"] == "usuario":
        if not _RE_USUARIO.match(p):
            raise AccionInvalida("Usuario inválido (letras, números, punto, guion; máx. 32).")
    else:
        p = ""
    plantilla = accion["plantillas"].get(marca) or accion["plantillas"].get("*")
    if not plantilla:
        raise AccionInvalida(f"La acción no está disponible para equipos {marca}.")
    return plantilla.format(p=p)
