"""
Equipo de red VIRTUAL para pruebas (emula la CLI básica de un router Cisco IOS).

Sirve para probar el gestor SSH/consola sin GNS3, y lo usan las pruebas automáticas.
Expone:
  * SSH    en 127.0.0.1:2222  (usuario y clave de las variables SSH_USUARIO / SSH_CLAVE, o noc/LabNoc2026x)
  * Telnet en 127.0.0.1:5099  (simula la consola de GNS3: pide Username/Password)
y, si se indica --syslog, envía Syslog al NOC cuando se configura algo (como un equipo real).

Uso:
    python tools/equipo_virtual.py
    python tools/equipo_virtual.py --syslog 127.0.0.1:5514 --nombre R-VIRTUAL
"""
import argparse
import os
import socket
import socketserver
import threading
from datetime import datetime

try:
    import paramiko
except ImportError:
    paramiko = None


class CLI:
    """Intérprete mínimo con estados: usuario (>), privilegiado (#) y configuración (config)#."""

    def __init__(self, nombre="R-VIRTUAL", syslog=None):
        self.nombre = nombre
        self.modo = "priv"
        self.syslog = syslog
        self.config = ["hostname " + nombre, "logging host 198.51.100.200"]
        self.interfaces = {"GigabitEthernet0/0": ["192.0.2.1", "up", "up"], "GigabitEthernet0/1": ["unassigned", "administratively down", "down"],
                           "GigabitEthernet0/2": ["unassigned", "down", "down"], "Loopback0": ["10.255.0.1", "up", "up"]}

    def nueva_sesion(self) -> "CLI":
        """Cada conexión tiene su propio modo, pero comparte la configuración del equipo."""
        sesion = CLI.__new__(CLI)
        sesion.__dict__.update(self.__dict__)
        sesion.modo = "priv"
        return sesion

    @property
    def prompt(self):
        return f"{self.nombre}(config)#" if self.modo == "config" else f"{self.nombre}#"

    def _syslog(self, sev, mnem, texto):
        if not self.syslog:
            return
        t = datetime.now()
        msg = f"<{23 * 8 + sev}>1: {self.nombre}: *{t:%b} {t.day:>2} {t:%H:%M:%S}.000: %{mnem}: {texto}"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(msg.encode(), self.syslog)

    def ejecutar(self, linea: str) -> str:
        cmd = " ".join(linea.split())
        if not cmd:
            return ""
        if self.modo == "config":
            if cmd in ("end", "exit"):
                self.modo = "priv"
                self._syslog(5, "SYS-5-CONFIG_I", "Configured from console by noc on vty0 (127.0.0.1)")
                return ""
            if "invalido" in cmd or cmd.startswith("xyz"):
                return "                ^\n% Invalid input detected at '^' marker."
            self.config.append(cmd)
            self._syslog(5, "PARSER-5-CFGLOG_LOGGEDCMD", f"User:noc logged command:{cmd}")
            return ""
        respuestas = {
            "terminal length 0": "",
            "show clock": datetime.now().strftime("*%H:%M:%S.000 COT %a %b %d %Y"),
            "show version": f"Cisco IOS Software, Virtual Router (EQUIPO VIRTUAL DE PRUEBAS)\n{self.nombre} uptime is 1 hour",
            "show running-config | include logging": "\n".join(l for l in self.config if "logging" in l),
            "show ip interface brief": "Interface              IP-Address      OK? Method Status                Protocol\n" + "\n".join(
                f"{n:<22} {v[0]:<15} YES NVRAM  {v[1]:<21} {v[2]}" for n, v in self.interfaces.items()),
            "show logging": "Syslog logging: enabled\n    Logging to 198.51.100.200 (udp port 514)",
            "show ntp status": "Clock is synchronized, stratum 3, reference is 198.51.100.123",
            "show users": "*  2 vty 0     noc        idle                 00:00:00 127.0.0.1",
            "show archive log config all": "\n".join(f"   {i}  1  noc@vty0 |{l}" for i, l in enumerate(self.config[2:], 1)) or "(vacío)",
        }
        if cmd == "configure terminal":
            self.modo = "config"
            return "Enter configuration commands, one per line.  End with CNTL/Z."
        if cmd in respuestas:
            return respuestas[cmd]
        return "                ^\n% Invalid input detected at '^' marker."


# ------------------------------------------------------------------- SSH
if paramiko:
    class _ServidorSSH(paramiko.ServerInterface):
        def __init__(self, usuario, clave):
            self.usuario, self.clave = usuario, clave
            self.evento = threading.Event()

        def check_auth_password(self, username, password):
            ok = username == self.usuario and password == self.clave
            return paramiko.AUTH_SUCCESSFUL if ok else paramiko.AUTH_FAILED

        def get_allowed_auths(self, username):
            return "password"

        def check_channel_request(self, kind, chanid):
            return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

        def check_channel_shell_request(self, channel):
            self.evento.set()
            return True

        def check_channel_pty_request(self, *args):
            return True


def _atender_ssh(cliente, llave, usuario, clave, fabrica_cli):
    t = paramiko.Transport(cliente)
    t.add_server_key(llave)
    servidor = _ServidorSSH(usuario, clave)
    try:
        t.start_server(server=servidor)
        canal = t.accept(10)
        if canal is None:
            return
        servidor.evento.wait(10)
        cli = fabrica_cli()
        canal.send(f"\r\n{cli.prompt}")
        buffer = ""
        while True:
            datos = canal.recv(1024)
            if not datos:
                break
            buffer += datos.decode("utf-8", "replace")
            while "\n" in buffer or "\r" in buffer:
                linea, _, buffer = buffer.replace("\r\n", "\n").replace("\r", "\n").partition("\n")
                salida = cli.ejecutar(linea)
                canal.send(f"{linea}\r\n" + (salida.replace("\n", "\r\n") + "\r\n" if salida else "") + cli.prompt)
    except Exception:
        pass
    finally:
        t.close()


def iniciar_ssh(host="127.0.0.1", puerto=2222, usuario="noc", clave="LabNoc2026x", fabrica_cli=None):
    """Arranca el servidor SSH en un hilo. Devuelve el puerto real (0 = aleatorio)."""
    if paramiko is None:
        raise RuntimeError("Falta paramiko")
    fabrica_cli = fabrica_cli or CLI().nueva_sesion
    llave = paramiko.RSAKey.generate(2048)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, puerto))
    sock.listen(5)

    def aceptar():
        while True:
            cliente, _ = sock.accept()
            threading.Thread(target=_atender_ssh, args=(cliente, llave, usuario, clave, fabrica_cli), daemon=True).start()

    threading.Thread(target=aceptar, daemon=True).start()
    return sock.getsockname()[1]


# ---------------------------------------------------------------- Telnet
class _ManejadorTelnet(socketserver.BaseRequestHandler):
    def _linea(self) -> str:
        datos = b""
        while not datos.endswith(b"\n"):
            b = self.request.recv(1)
            if not b:
                raise ConnectionError
            if b == b"\xff":           # comando telnet: se ignora (3 bytes)
                self.request.recv(2)
                continue
            datos += b
        return datos.decode("utf-8", "replace").strip()

    def handle(self):
        srv = self.server
        try:
            self.request.sendall(b"\xff\xfb\x01\xff\xfb\x03")   # IAC WILL ECHO, IAC WILL SGA (como GNS3)
            self.request.sendall(b"\r\nUser Access Verification\r\n\r\nUsername: ")
            usuario = self._linea()
            if usuario == "":
                usuario = self._linea()
            self.request.sendall(b"Password: ")
            clave = self._linea()
            if (usuario, clave) != (srv.usuario, srv.clave):
                self.request.sendall(b"\r\n% Authentication failed\r\n")
                return
            cli = srv.fabrica_cli()
            self.request.sendall(f"\r\n{cli.prompt}".encode())
            while True:
                linea = self._linea()
                salida = cli.ejecutar(linea)
                self.request.sendall((f"{linea}\r\n" + (salida.replace("\n", "\r\n") + "\r\n" if salida else "") + cli.prompt).encode())
        except (ConnectionError, OSError):
            pass


def iniciar_telnet(host="127.0.0.1", puerto=5099, usuario="noc", clave="LabNoc2026x", fabrica_cli=None):
    fabrica_cli = fabrica_cli or CLI().nueva_sesion
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer((host, puerto), _ManejadorTelnet)
    srv.daemon_threads = True
    srv.usuario, srv.clave, srv.fabrica_cli = usuario, clave, fabrica_cli
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def main():
    p = argparse.ArgumentParser(description="Equipo Cisco virtual para pruebas del NOC")
    p.add_argument("--ssh", type=int, default=2222)
    p.add_argument("--telnet", type=int, default=5099)
    p.add_argument("--nombre", default="R-VIRTUAL")
    p.add_argument("--syslog", help="host:puerto del NOC para enviar Syslog, ej. 127.0.0.1:5514")
    a = p.parse_args()
    usuario = os.getenv("SSH_USUARIO") or "noc"
    clave = os.getenv("SSH_CLAVE") or "LabNoc2026x"
    syslog = None
    if a.syslog:
        h, pt = a.syslog.rsplit(":", 1)
        syslog = (h, int(pt))
    fabrica = CLI(a.nombre, syslog).nueva_sesion   # SSH y telnet comparten el mismo "equipo"
    print(f"Equipo virtual {a.nombre}")
    print(f"  SSH    127.0.0.1:{iniciar_ssh(puerto=a.ssh, usuario=usuario, clave=clave, fabrica_cli=fabrica)}")
    print(f"  Telnet 127.0.0.1:{iniciar_telnet(puerto=a.telnet, usuario=usuario, clave=clave, fabrica_cli=fabrica)}")
    print(f"  Usuario: {usuario}   (la clave es la de SSH_CLAVE en .env)")
    print("Ctrl + C para detener.")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
