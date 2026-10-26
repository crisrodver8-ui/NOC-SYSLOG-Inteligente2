"""
Consola SIMULADA de solo lectura (tipo PuTTY).

En el MVP no se conecta a ningún equipo: devuelve salidas de ejemplo.
Lo importante es la política de comandos:

  * LISTA PERMITIDA: solo comandos de consulta exactos por fabricante.
  * LISTA BLOQUEADA: comandos que cambian, borran o reinician el equipo.
  * Encadenamiento bloqueado: ; | && ` $( > no se aceptan.
  * Todo intento (permitido o bloqueado) queda en la auditoría.
"""
import re
from datetime import datetime

PERMITIDOS = {
    "Cisco": ["show version", "show clock", "show ip interface brief", "show logging",
              "show ntp status", "show running-config | include logging", "show users", "show archive log config all"],
    "Huawei": ["display version", "display clock", "display interface brief", "display info-center",
               "display ntp-service status", "display logbuffer", "display users"],
    "Fortinet": ["get system status", "get system interface", "get log syslogd setting",
                 "diagnose sys ntp status", "get system admin list"],
    "Otro": ["uptime", "hostname", "date"],
}

# Patrones peligrosos: se bloquean SIEMPRE, aunque alguien los agregue por error a la lista permitida
BLOQUEADOS = [re.compile(p, re.I) for p in (
    r"^\s*conf(ig(ure)?)?(\s+t(erminal)?)?\b", r"^\s*system-view\b", r"^\s*config\s+\w+",
    r"\breload\b", r"\breboot\b", r"\bwrite\s+(erase|memory)?\b", r"\berase\b", r"\bdelete\b",
    r"\bformat\b", r"\bfactoryreset\b", r"^\s*no\s+", r"^\s*undo\s+", r"\bshutdown\b",
    r"^\s*copy\b", r"^\s*debug\b", r"^\s*execute\b", r"^\s*set\s+", r"^\s*username\b",
    r"^\s*clear\b", r"^\s*reset\b", r"^\s*save\b",
)]
ENCADENAMIENTO = re.compile(r"[;`]|&&|\$\(|>|\|\|")


def normalizar(comando: str) -> str:
    return " ".join((comando or "").split())


def validar(marca: str, comando: str) -> tuple[bool, str]:
    """Devuelve (permitido, motivo)."""
    cmd = normalizar(comando)
    if not cmd:
        return False, "Comando vacío."
    if len(cmd) > 120:
        return False, "Comando demasiado largo."
    if ENCADENAMIENTO.search(cmd):
        return False, "BLOQUEADO: no se permite encadenar o redirigir comandos."
    if any(p.search(cmd) for p in BLOQUEADOS):
        return False, "BLOQUEADO: el comando modifica, borra o reinicia el equipo. La consola es de solo lectura."
    if cmd.lower() not in [c.lower() for c in PERMITIDOS.get(marca, [])]:
        return False, "NO PERMITIDO: el comando no está en la lista permitida para este fabricante."
    return True, "Permitido (lista de solo lectura)."


def salida_simulada(disp: dict, comando: str) -> str:
    """Respuestas de ejemplo construidas con los datos del inventario."""
    cmd = normalizar(comando).lower()
    n, ip, ver, mod = disp["nombre"], disp["ip"], disp["version"], disp["modelo"]
    reloj = datetime.now().strftime("%H:%M:%S.%f")[:-3] + " COT " + datetime.now().strftime("%a %b %d %Y")
    cab = "[SALIDA SIMULADA - v0.2.0]\n"
    tabla = {
        "show version": f"Cisco IOS XE Software, Version {ver}\n{n} uptime is 12 days, 4 hours, 31 minutes\ncisco {mod} processor with 1795979K/6147K bytes of memory.",
        "show clock": f"*{reloj}",
        "show ip interface brief": f"Interface              IP-Address      OK? Method Status    Protocol\nGigabitEthernet0/0/0   {ip:<15} YES NVRAM  up        up\nGigabitEthernet0/0/1   unassigned      YES unset  down      down\nLoopback0              10.255.0.1      YES NVRAM  up        up",
        "show logging": "Syslog logging: enabled (0 messages dropped, 0 flushes, 0 overruns)\n    Trap logging: level informational, 214 message lines logged\n        Logging to 198.51.100.200 (udp port 514), 214 message lines logged",
        "show ntp status": "Clock is synchronized, stratum 3, reference is 198.51.100.123\nnominal freq is 250.0000 Hz, actual freq is 250.0001 Hz",
        "show running-config | include logging": "logging trap informational\nlogging facility local7\nlogging source-interface Loopback0\nlogging host 198.51.100.200",
        "show users": "    Line       User       Host(s)              Idle       Location\n*  2 vty 0     noc.admin  idle                 00:00:00 198.51.100.50",
        "show archive log config all": " idx   sess           user@line      Logged command\n    1     1      noc.admin@vty0     |logging host 198.51.100.200",
        "display version": f"Huawei Versatile Routing Platform Software\nVRP (R) software, Version {ver}\nHUAWEI {mod} uptime is 30 days, 2 hours, 10 minutes",
        "display clock": reloj,
        "display interface brief": f"Interface                   PHY   Protocol InUti OutUti\nGigabitEthernet0/0/1        up    up       0.5%  0.3%\nGigabitEthernet0/0/2        down  down        0%    0%\nVlanif1 ({ip})        up    up          --    --",
        "display info-center": "Information Center: enabled\nLog host:\n  198.51.100.200, channel number 2, channel name loghost, language English, host facility local7",
        "display ntp-service status": "clock status: synchronized\nclock stratum: 3\nreference clock ID: 198.51.100.123",
        "display logbuffer": "Logging buffer configuration and contents: enabled\nAllowed max buffer size: 1024\nActual buffer size: 512",
        "display users": "  User-Intf    Delay    Type   Network Address     AuthenStatus\n+ 34  VTY 0   00:00:00  SSH    198.51.100.50       pass",
        "get system status": f"Version: {mod} v{ver.replace('FortiOS ', '')}\nHostname: {n}\nOperation Mode: NAT\nSystem time: {reloj}",
        "get system interface": f"== [ wan1 ]\nname: wan1   mode: static    ip: {ip} 255.255.255.0   status: up\n== [ internal ]\nname: internal   ip: 192.168.1.99 255.255.255.0   status: up",
        "get log syslogd setting": 'status              : enable\nserver              : "198.51.100.200"\nmode                : udp\nport                : 514\nfacility            : local7',
        "diagnose sys ntp status": "synchronized: yes, ntpsync: enabled, server-mode: disabled\nipv4 server(198.51.100.123) -- reachable(0xff) S:1 T:32",
        "get system admin list": "name        profile         vdom    trusthost\nnoc.admin   super_admin     root    198.51.100.0/24",
        "uptime": " 10:14:02 up 5 days,  3:12,  1 user,  load average: 0.08, 0.05, 0.01",
        "hostname": n,
        "date": reloj,
    }
    return cab + tabla.get(cmd, "(sin salida simulada)")
