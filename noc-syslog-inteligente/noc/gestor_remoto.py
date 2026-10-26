"""
Gestor de conexiones REALES a los equipos (v1.0.0), siempre desde el backend.

Transportes:
  ssh      SSH (paramiko) a la IP del equipo. Recomendado.
  consola  Telnet a la consola de GNS3/EVE-NG (ej. 127.0.0.1:5002). Solo a hosts de
           la lista CONSOLA_HOSTS_PERMITIDOS (por defecto solo este PC).

Controles de seguridad:
  * LISTA DE HOSTS: solo equipos del inventario autorizados, no simulados y con gestión habilitada.
  * LISTA DE COMANDOS: las consultas pasan por consola.validar() (solo lectura).
  * Los CAMBIOS solo entran por acciones del catálogo APROBADAS por un supervisor.
  * Credenciales en .env (SSH_USUARIO / SSH_CLAVE o SSH_CLAVE_<NOMBRE_EQUIPO>); nunca en la BD.
  * Huella de la llave SSH guardada la primera vez (TOFU): si cambia, se rechaza la conexión.
  * Tiempos de espera y tamaño máximo de salida.
"""
import os
import re
import socket
import time

try:
    import paramiko
except ImportError:  # el resto de la app funciona sin paramiko
    paramiko = None

RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][A-Z0-9]")
# Prompt de Cisco (R1# / R1>), Huawei (<R1> / [R1]) y Fortinet (FGT # / FGT $)
RE_PROMPT = re.compile(r"(?:^|\n)[^\n]{0,60}(?:[#>$]|\])\s*$")
RE_USUARIO = re.compile(r"(user ?name|login)\s*:\s*$", re.I)
RE_CLAVE = re.compile(r"password\s*:\s*$", re.I)
SALIDA_MAX = 20000

PAGINACION = {"Cisco": "terminal length 0", "Huawei": "screen-length 0 temporary"}
MODO_CONFIG = {
    "Cisco": (["configure terminal"], ["end"]),
    "Huawei": (["system-view"], ["return"]),
    "Fortinet": ([], []),          # las plantillas de FortiOS ya traen config ... end
}


class ErrorGestion(Exception):
    pass


def _var(nombre_equipo: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", nombre_equipo.upper())


def credenciales(cfg: dict, disp: dict) -> tuple[str, str]:
    """Credenciales del equipo: primero SSH_*_<NOMBRE>, si no, las generales. Solo desde el entorno."""
    sufijo = _var(disp["nombre"])
    usuario = os.getenv(f"SSH_USUARIO_{sufijo}") or cfg.get("SSH_USUARIO", "")
    clave = os.getenv(f"SSH_CLAVE_{sufijo}") or cfg.get("SSH_CLAVE", "")
    return usuario, clave


def validar_destino(cfg: dict, disp: dict) -> tuple[str, str, int]:
    """Aplica la LISTA DE HOSTS. Devuelve (transporte, host, puerto)."""
    if not disp["autorizado"]:
        raise ErrorGestion("El equipo no está en la lista permitida.")
    if disp["simulado"]:
        raise ErrorGestion("El equipo es simulado: no tiene conexión real.")
    if disp["gestion"] == "ssh":
        return "ssh", disp["ip"], int(disp["ssh_puerto"] or 22)
    if disp["gestion"] == "consola":
        if disp["consola_tipo"] != "telnet" or ":" not in disp["consola_destino"]:
            raise ErrorGestion("La consola del equipo no es telnet (formato host:puerto).")
        host, puerto = disp["consola_destino"].rsplit(":", 1)
        if host not in cfg["CONSOLA_HOSTS_PERMITIDOS"]:
            raise ErrorGestion(f"El host de consola {host} no está en CONSOLA_HOSTS_PERMITIDOS.")
        return "consola", host, int(puerto)
    raise ErrorGestion("El equipo no tiene la gestión remota habilitada (SSH o consola).")


# ----------------------------------------------------------------- sesiones
class _Sesion:
    """Interfaz común: enviar texto y leer hasta el prompt."""

    def enviar(self, texto: str): raise NotImplementedError
    def _recibir(self) -> str: raise NotImplementedError
    def cerrar(self): raise NotImplementedError

    def leer_hasta_prompt(self, timeout: float) -> str:
        fin = time.monotonic() + timeout
        buffer = ""
        while time.monotonic() < fin:
            trozo = self._recibir()
            if trozo:
                buffer += trozo
                if len(buffer) > SALIDA_MAX * 2:
                    break
                limpio = RE_ANSI.sub("", buffer).replace("\r", "")
                if RE_PROMPT.search(limpio) or RE_USUARIO.search(limpio) or RE_CLAVE.search(limpio):
                    # pequeña espera por si llega más texto
                    time.sleep(0.15)
                    extra = self._recibir()
                    if not extra:
                        break
                    buffer += extra
            else:
                time.sleep(0.05)
        return RE_ANSI.sub("", buffer).replace("\r", "")


class _SesionSSH(_Sesion):
    def __init__(self, host, puerto, usuario, clave, timeout, known_hosts):
        if paramiko is None:
            raise ErrorGestion("Falta la librería paramiko (pip install -r requirements.txt).")
        self.cliente = paramiko.SSHClient()
        if os.path.exists(known_hosts):
            self.cliente.load_host_keys(known_hosts)
        # TOFU: la primera vez se guarda la llave; si después cambia, paramiko rechaza (BadHostKeyException)
        self.cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            self.cliente.connect(host, port=puerto, username=usuario, password=clave, timeout=timeout,
                                 banner_timeout=timeout, auth_timeout=timeout, look_for_keys=False, allow_agent=False)
        except paramiko.BadHostKeyException:
            raise ErrorGestion("¡La llave SSH del equipo cambió! Posible suplantación. Conexión rechazada.")
        except paramiko.AuthenticationException:
            raise ErrorGestion("Usuario o clave SSH incorrectos (revisa .env).")
        except (OSError, paramiko.SSHException) as e:
            raise ErrorGestion(f"No se pudo conectar por SSH a {host}:{puerto} ({e.__class__.__name__}).")
        self.cliente.save_host_keys(known_hosts)
        self.canal = self.cliente.invoke_shell(width=200, height=1000)
        self.canal.settimeout(0.0)

    def enviar(self, texto):
        try:
            self.canal.send(texto + "\n")
        except OSError:
            raise ErrorGestion("El equipo cerró la sesión SSH.")

    def _recibir(self):
        try:
            if self.canal.recv_ready():
                return self.canal.recv(65535).decode("utf-8", "replace")
        except OSError:
            pass
        return ""

    def cerrar(self):
        self.cliente.close()


class _SesionTelnet(_Sesion):
    """Cliente telnet mínimo (telnetlib ya no existe en Python 3.13+)."""
    IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

    def __init__(self, host, puerto, timeout):
        try:
            self.sock = socket.create_connection((host, puerto), timeout=timeout)
        except OSError as e:
            raise ErrorGestion(f"No se pudo abrir la consola {host}:{puerto} ({e.__class__.__name__}). "
                               "¿Está encendido el equipo en GNS3?")
        self.sock.setblocking(False)

    def _negociar(self, datos: bytes) -> bytes:
        """Quita los comandos telnet (IAC) y rechaza todas las opciones."""
        salida, i = bytearray(), 0
        while i < len(datos):
            b = datos[i]
            if b == self.IAC and i + 1 < len(datos):
                cmd = datos[i + 1]
                if cmd in (self.DO, self.DONT, self.WILL, self.WONT) and i + 2 < len(datos):
                    opcion = datos[i + 2]
                    respuesta = self.WONT if cmd == self.DO else self.DONT if cmd == self.WILL else None
                    if respuesta:
                        try:
                            self.sock.sendall(bytes([self.IAC, respuesta, opcion]))
                        except OSError:
                            pass
                    i += 3
                    continue
                if cmd == self.SB:
                    fin = datos.find(bytes([self.IAC, self.SE]), i)
                    i = len(datos) if fin < 0 else fin + 2
                    continue
                i += 2
                continue
            salida.append(b)
            i += 1
        return bytes(salida)

    def enviar(self, texto):
        try:
            self.sock.sendall((texto + "\r\n").encode())
        except OSError:
            raise ErrorGestion("La consola cerró la conexión (¿usuario o clave incorrectos?).")

    def _recibir(self):
        try:
            datos = self.sock.recv(65535)
        except (BlockingIOError, OSError):
            return ""
        return self._negociar(datos).decode("utf-8", "replace") if datos else ""

    def cerrar(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ------------------------------------------------------------------ API
def abrir_sesion(cfg: dict, disp: dict) -> _Sesion:
    transporte, host, puerto = validar_destino(cfg, disp)
    usuario, clave = credenciales(cfg, disp)
    timeout = cfg.get("SSH_TIMEOUT_S", 8)
    if transporte == "ssh":
        if not usuario or not clave:
            raise ErrorGestion("Faltan SSH_USUARIO y SSH_CLAVE en el archivo .env.")
        known = os.path.join(os.path.dirname(cfg["DB_PATH"]), "known_hosts")
        sesion = _SesionSSH(host, puerto, usuario, clave, timeout, known)
        sesion.leer_hasta_prompt(timeout)
    else:
        sesion = _SesionTelnet(host, puerto, timeout)
        sesion.enviar("")
        texto = sesion.leer_hasta_prompt(timeout)
        # Si la consola pide usuario/clave, se usan las credenciales del .env
        if RE_USUARIO.search(texto):
            sesion.enviar(usuario)
            texto = sesion.leer_hasta_prompt(timeout)
        if RE_CLAVE.search(texto):
            sesion.enviar(clave)
            texto = sesion.leer_hasta_prompt(timeout)
        if re.search(r"authentication failed|login invalid|access denied", texto, re.I) or not RE_PROMPT.search(texto):
            sesion.cerrar()
            raise ErrorGestion("La consola rechazó el usuario o la clave (revisa SSH_USUARIO / SSH_CLAVE en .env).")
    if disp["marca"] in PAGINACION:
        sesion.enviar(PAGINACION[disp["marca"]])
        sesion.leer_hasta_prompt(timeout)
    return sesion


def _limpiar_salida(salida: str, comando: str) -> str:
    lineas = salida.split("\n")
    if lineas and comando.strip() and comando.strip() in lineas[0]:
        lineas = lineas[1:]                    # eco del comando
    if lineas and RE_PROMPT.search(lineas[-1]):
        lineas = lineas[:-1]                   # prompt final
    return "\n".join(lineas).strip()[:SALIDA_MAX]


def ejecutar_consulta(cfg: dict, disp: dict, comando: str, sesion_fn=abrir_sesion) -> str:
    """Ejecuta UN comando de consulta (ya validado contra la lista permitida)."""
    sesion = sesion_fn(cfg, disp)
    try:
        sesion.enviar(comando)
        return _limpiar_salida(sesion.leer_hasta_prompt(cfg.get("SSH_TIMEOUT_S", 8)), comando)
    finally:
        sesion.cerrar()


def ejecutar_cambio(cfg: dict, disp: dict, lineas: list[str], modo: str = "config", sesion_fn=abrir_sesion) -> str:
    """Aplica líneas de una acción APROBADA y devuelve la transcripción (modo config o exec)."""
    entrada, salida_modo = MODO_CONFIG.get(disp["marca"], ([], [])) if modo == "config" else ([], [])
    sesion = sesion_fn(cfg, disp)
    transcripcion = []
    try:
        for linea in entrada + [l for l in lineas if l.strip() and not l.lstrip().startswith("!")] + salida_modo:
            sesion.enviar(linea)
            respuesta = sesion.leer_hasta_prompt(cfg.get("SSH_TIMEOUT_S", 8))
            transcripcion.append(respuesta.strip())
            if re.search(r"% ?Invalid|% ?Incomplete|Error:|Unrecognized command|command parse error", respuesta, re.I):
                transcripcion.append(f"!! El equipo rechazó la línea: {linea}")
                raise ErrorGestion("El equipo rechazó un comando:\n" + "\n".join(transcripcion)[-2000:])
        return "\n".join(transcripcion)[:SALIDA_MAX]
    finally:
        sesion.cerrar()
