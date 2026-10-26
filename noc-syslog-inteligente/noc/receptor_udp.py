"""
Receptor Syslog por UDP.

Corre en un hilo aparte para no bloquear la interfaz web. Cada datagrama
recibido se entrega al Ingestor junto con la IP REAL de origen del paquete
(esa IP es la que se compara con la lista permitida).
"""
import logging
import socket
import threading

from .db import connect

log = logging.getLogger("noc.receptor")
estado = {"activo": False, "puerto": None, "error": None}


def _bucle(app, sock: socket.socket):
    conn = connect(app.config["DB_PATH"])  # conexión propia del hilo
    ingestor = app.extensions["ingestor"]
    while True:
        try:
            datos, (ip, _puerto) = sock.recvfrom(8192)
            ingestor.procesar(conn, datos.decode("utf-8", errors="replace"), ip, "udp")
        except Exception as exc:  # un mensaje malo nunca debe tumbar el receptor
            log.exception("Error procesando datagrama: %s", exc)


def iniciar(app) -> bool:
    host, puerto = app.config["SYSLOG_HOST"], app.config["SYSLOG_PORT"]
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, puerto))
    except OSError as exc:
        estado.update(activo=False, error=f"No se pudo abrir UDP {host}:{puerto} ({exc})")
        log.error(estado["error"])
        return False
    threading.Thread(target=_bucle, args=(app, sock), daemon=True, name="receptor-syslog").start()
    estado.update(activo=True, puerto=puerto, error=None)
    log.info("Receptor Syslog escuchando en UDP %s:%s", host, puerto)
    return True
