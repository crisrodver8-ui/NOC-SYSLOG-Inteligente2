"""
Puertos (interfaces) de los equipos.

- normalizar(): "Gi0/1", "GE0/0/1" y "GigabitEthernet0/1" se reconocen como el mismo puerto.
- estado_desde_syslog(): detecta en un mensaje Syslog qué puerto cambió y a qué estado.
- parsear_salida(): lee la salida de "show ip interface brief" (Cisco),
  "display interface brief" (Huawei) o "get system interface" (Fortinet).
"""
import re

# Abreviaturas comunes -> nombre completo
_ABREVIATURAS = [
    (r"^(te|tengig|tengigabitethernet)", "tengigabitethernet"),
    (r"^(xge|xgigabitethernet)", "xgigabitethernet"),
    (r"^(gi|ge|gig|gigabitethernet)", "gigabitethernet"),
    (r"^(fa|fastethernet)", "fastethernet"),
    (r"^(eth|ethernet)", "ethernet"),
    (r"^(lo|loopback)", "loopback"),
    (r"^(vl|vlan|vlanif)", "vlan"),
    (r"^(po|port-channel|eth-trunk)", "port-channel"),
]


def normalizar(nombre: str) -> str:
    n = re.sub(r"\s+", "", (nombre or "").strip().lower())
    for patron, completo in _ABREVIATURAS:
        m = re.match(patron + r"(?=[\d/.:]|$)", n)
        if m:
            return completo + n[m.end():]
    return n


# --- Mensajes Syslog que informan cambios de puerto ---
_PATRONES_SYSLOG = [
    # Cisco: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to down
    (re.compile(r"%LINK-\d-UPDOWN: Interface ([\w/.\-]+), changed state to (up|down|administratively down)", re.I), None),
    # Cisco: %LINEPROTO-5-UPDOWN: Line protocol on Interface X, changed state to up
    (re.compile(r"Line protocol on Interface ([\w/.\-]+), changed state to (up|down)", re.I), None),
    # Huawei: Interface GigabitEthernet0/0/1 has turned into DOWN state.
    (re.compile(r"Interface ([\w/.\-]+) has turned into (UP|DOWN) state", re.I), None),
    # Fortinet: Link monitor: Interface wan1 was turned up
    (re.compile(r"Interface ([\w/.\-]+) was turned (up|down)", re.I), None),
]


def estado_desde_syslog(mensaje: str) -> tuple[str, str] | None:
    """Devuelve (nombre_puerto, estado) o None si el mensaje no habla de un puerto."""
    for patron, _ in _PATRONES_SYSLOG:
        m = patron.search(mensaje)
        if m:
            estado = m.group(2).lower()
            return m.group(1), ("admin_down" if "administratively" in estado else estado)
    return None


# --- Salidas de comandos de consulta ---
def _estado(phy: str, protocolo: str = "") -> str:
    phy, protocolo = phy.lower(), protocolo.lower()
    if "admin" in phy or phy.startswith("*down"):
        return "admin_down"
    if phy.startswith("up") and (not protocolo or protocolo.startswith("up")):
        return "up"
    if phy.startswith("up") or phy.startswith("down"):
        return "down"
    return "desconocido"


def parsear_salida(marca: str, salida: str) -> list[dict]:
    """Convierte la salida de un comando de interfaces en una lista de puertos."""
    puertos = []
    for linea in salida.splitlines():
        partes = linea.split()
        if not partes:
            continue
        if marca == "Cisco":
            # Interface  IP-Address  OK?  Method  Status  Protocol
            m = re.match(r"^(\S+)\s+(\S+)\s+(YES|NO)\s+\S+\s+(administratively down|up|down)\s+(up|down)", linea, re.I)
            if m:
                ip = "" if m.group(2) == "unassigned" else m.group(2)
                puertos.append({"nombre": m.group(1), "ip": ip, "estado": _estado(
                    "admin" if "admin" in m.group(4).lower() else m.group(4), m.group(5))})
        elif marca == "Huawei":
            # Interface  PHY  Protocol  InUti OutUti ...
            m = re.match(r"^(\S+?)(?:\(\w+\))?\s+(\*down|\^down|up|down)\s+(up|down|up\(s\))", linea, re.I)
            if m and not linea.lower().startswith("interface"):
                puertos.append({"nombre": m.group(1), "ip": "", "estado": _estado(m.group(2), m.group(3))})
        elif marca == "Fortinet":
            # name: wan1   mode: static    ip: 1.2.3.4 255.255.255.0   status: up
            m = re.search(r"name:\s*(\S+).*?ip:\s*(\S+)\s+\S+.*?status:\s*(up|down)", linea, re.I)
            if m:
                puertos.append({"nombre": m.group(1), "ip": "" if m.group(2) == "0.0.0.0" else m.group(2),
                                "estado": m.group(3).lower()})
    return puertos


COMANDO_INTERFACES = {
    "Cisco": "show ip interface brief",
    "Huawei": "display interface brief",
    "Fortinet": "get system interface",
}
