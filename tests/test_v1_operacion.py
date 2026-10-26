"""
Pruebas de v1.0.0: defensa IA mejorada, puertos desde Syslog, Telegram, verificación
de políticas, carga básica, respaldo y recuperación.
"""
import os
import sys
import time
from datetime import datetime, timedelta

import pytest

from conftest import cab

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ingerir(app, texto, ip="198.51.100.1", origen="udp"):
    from noc.db import connect
    conn = connect(app.config["DB_PATH"])
    r = app.extensions["ingestor"].procesar(conn, texto, ip, origen)
    conn.close()
    return r


def _bsd(t):
    return f"{t:%b} {t.day:>2} {t:%H:%M:%S}"


# ------------------------------------------------------------- defensa IA
def test_hora_desfasada_y_horario_con_hora_del_colector(app):
    falsa = datetime.now() - timedelta(hours=7)
    r = _ingerir(app, f"<189>1: *{_bsd(falsa)}.000: %LINK-5-CHANGED: Interface Gi0/0/1, changed state to up")
    assert "hora_desfasada" in r["banderas"] and r["riesgo"] > 0


def test_hora_correcta_no_se_marca(app):
    r = _ingerir(app, f"<189>1: *{_bsd(datetime.now())}.000: %LINK-5-CHANGED: Interface Gi0/0/1, changed state to up")
    assert "hora_desfasada" not in r["banderas"]


def test_cambio_sin_accion_aprobada_es_no_autorizado(app, cliente):
    texto = f"<189>1: *{_bsd(datetime.now())}.000: %SYS-5-CONFIG_I: Configured from console by admin on vty0"
    r = _ingerir(app, texto)
    assert "cambio_no_autorizado" in r["banderas"] and r["incidente_id"]
    # Con una acción aprobada para el equipo, el cambio queda respaldado por el flujo
    aid = cliente.post("/api/acciones", headers=cab(), json={"dispositivo_id": 1, "tipo": "observar",
                                                             "justificacion": "Cambio planificado"}).json["id"]
    cliente.post(f"/api/acciones/{aid}/revisar", headers=cab("supervisor1"), json={"decision": "aprobar"})
    r2 = _ingerir(app, texto.replace("admin", "noc.admin"))
    assert "cambio_no_autorizado" not in r2["banderas"]


def test_rafaga_de_cambios(app):
    resultados = [_ingerir(app, f"<189>{i}: *{_bsd(datetime.now())}.000: %PARSER-5-CFGLOG_LOGGEDCMD: "
                                f"User:bot-x logged command:interface Gi0/{i}") for i in range(6)]
    assert "rafaga_cambios" in resultados[-1]["banderas"]


def test_ataque_ia_completo_genera_todas_las_alertas(cliente):
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "ataque_ia"})
    banderas = ",".join(e["banderas"] for e in cliente.get("/api/eventos?sospechoso=1&limite=100", headers=cab()).json["items"])
    for b in ("fuerza_bruta", "posible_inyeccion", "ofuscacion", "rafaga_cambios", "cambio_no_autorizado",
              "fuente_no_autorizada", "hora_desfasada", "cuenta_servicio"):
        assert b in banderas, b
    altos = cliente.get("/api/eventos?riesgo_min=60", headers=cab()).json["total"]
    assert altos >= 3


# --------------------------------------------------------------- puertos
def test_syslog_actualiza_estado_del_puerto(app, cliente):
    _ingerir(app, f"<187>1: *{_bsd(datetime.now())}.000: %LINK-3-UPDOWN: Interface GigabitEthernet0/0/0, changed state to down")
    puertos = {p["nombre"]: p for p in cliente.get("/api/dispositivos/1", headers=cab()).json["interfaces"]}
    assert puertos["GigabitEthernet0/0/0"]["estado"] == "down"


def test_crud_de_puertos_y_consola(cliente):
    r = cliente.post("/api/dispositivos", headers=cab(), json={
        "nombre": "SW-GNS3", "ip": "192.0.2.50", "marca": "Cisco", "consola_tipo": "serial", "consola_destino": "COM7",
        "consola_velocidad": 9600})
    did = r.json["id"]
    assert cliente.post(f"/api/dispositivos/{did}/interfaces", headers=cab(),
                        json={"nombre": "Gi0/1", "tipo": "cobre", "estado": "up", "ip": "10.0.0.1/24", "conectado_a": "R1 Gi0/0"}).status_code == 201
    # Mismo puerto con otro nombre (abreviado/completo) = duplicado
    assert cliente.post(f"/api/dispositivos/{did}/interfaces", headers=cab(), json={"nombre": "GigabitEthernet0/1"}).status_code == 409
    assert cliente.post(f"/api/dispositivos/{did}/interfaces", headers=cab(), json={"nombre": "Gi0/2", "ip": "999.1.1.1"}).status_code == 400
    # Validación de la consola
    malo = cliente.post("/api/dispositivos", headers=cab(), json={"nombre": "SW-X", "ip": "192.0.2.51", "marca": "Cisco",
                                                                   "consola_tipo": "telnet", "consola_destino": "sin-puerto"})
    assert malo.status_code == 400
    d = cliente.get(f"/api/dispositivos/{did}", headers=cab()).json
    assert d["consola_destino"] == "COM7" and len(d["interfaces"]) == 1


def test_semilla_trae_puertos_y_consolas(cliente):
    equipos = cliente.get("/api/dispositivos", headers=cab()).json
    assert all(e["puertos"] > 0 for e in equipos if e["nombre"] != "LAB-LOCALHOST")
    assert any(e["consola_tipo"] == "serial" for e in equipos) and any(e["consola_tipo"] == "telnet" for e in equipos)


# --------------------------------------------------------------- Telegram
def test_telegram_alerta_sin_exponer_token(tmp_path):
    from noc import db
    from noc.notificador import NotificadorTelegram, enmascarar
    ruta = str(tmp_path / "t.db")
    conn = db.connect(ruta)
    db.init_db(conn)
    enviados = []
    n = NotificadorTelegram("123456:SECRETO-ABC", "999", ruta, limite_min=2,
                            enviar_fn=lambda texto: (enviados.append(texto) or True, "Enviada"))
    n.iniciar()
    assert n.alertar("Alerta 1", ["<b>log</b> malicioso"]) is True
    assert n.alertar("Alerta 1", ["repetida"]) is False          # deduplicada
    n.alertar("Alerta 2", ["x"])
    n.alertar("Alerta 3", ["x"])                                   # supera el límite por minuto
    time.sleep(0.5)
    assert len(enviados) == 2
    assert "&lt;b&gt;log" in enviados[0]                           # el log se escapa
    assert "SECRETO" not in enmascarar("123456:SECRETO-ABC")
    estados = [r["estado"] for r in conn.execute("SELECT estado FROM notificaciones")]
    assert estados.count("enviada") == 2 and "omitida" in estados


def test_telegram_no_configurado(cliente):
    r = cliente.get("/api/telegram", headers=cab("supervisor1")).json
    assert r["configurado"] is False and r["token"] == ""
    assert cliente.post("/api/telegram/prueba", headers=cab("admin"), json={}).status_code == 502


# ------------------------------------------------------------ verificación
def test_verificacion_de_politicas(cliente):
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "normal", "cantidad": 40})
    v = cliente.get("/api/verificacion", headers=cab()).json
    assert v["globales"]["Fechas inmutables"]["estado"] == "ok"
    assert v["globales"]["Integridad de la auditoría"]["estado"] == "ok"
    equipo = next(e for e in v["equipos"] if e["nombre"] == "LAB-RT-BORDE01")
    assert equipo["chequeos"]["Lista permitida"]["estado"] == "ok"
    assert equipo["chequeos"]["Consola documentada"]["estado"] == "ok"


# ------------------------------------------------------------------ carga
def test_carga_basica_2000_mensajes(app):
    """2000 mensajes de 20 fuentes deben procesarse en menos de 20 s (≥ 100 msg/s)."""
    from noc.db import connect
    app.extensions["ingestor"].limitador.limite = 10_000
    conn = connect(app.config["DB_PATH"])
    ingestor = app.extensions["ingestor"]
    inicio = time.perf_counter()
    for i in range(2000):
        ingestor.procesar(conn, f"<190>{_bsd(datetime.now())} LAB-SW-DIST01 carga[{i}]: mensaje {i % 300}",
                          f"198.51.100.{10 + i % 20}", "udp")
    duracion = time.perf_counter() - inicio
    conn.close()
    assert duracion < 20, f"{2000 / duracion:.0f} msg/s"


# ------------------------------------------------------ respaldo / recuperación
def test_respaldo_y_recuperacion(app, cliente, tmp_path):
    from tools.respaldo import crear_respaldo
    from tools.restaurar import restaurar, verificar
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "ataque_ia"})
    total_antes = cliente.get("/api/eventos", headers=cab()).json["total"]
    r = crear_respaldo(app.config["DB_PATH"], str(tmp_path / "respaldos"))
    assert r["conteos"]["eventos"] == total_antes
    # Desastre: se pierde la base de datos
    destino = str(tmp_path / "restaurada" / "noc.db")
    restaurar(r["archivo"], destino)
    from noc.db import connect, verificar_cadena
    conn = connect(destino)
    assert conn.execute("SELECT COUNT(*) FROM eventos").fetchone()[0] == total_antes
    assert verificar_cadena(conn)["integra"]
    # Un respaldo alterado se rechaza
    with open(r["archivo"], "ab") as f:
        f.write(b"basura")
    with pytest.raises(RuntimeError, match="SHA-256"):
        verificar(r["archivo"])


# ------------------------------------------------------------- hora NTP
def test_cliente_ntp_mide_el_desfase():
    """Servidor NTP falso adelantado 1,5 s: el cliente debe medir ~1500 ms."""
    import socket
    import struct
    import threading
    from noc import hora

    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    puerto = srv.getsockname()[1]

    def responder():
        _, cliente = srv.recvfrom(48)
        t = time.time() + 1.5 + 2208988800
        seg, frac = int(t), int((t % 1) * 2**32)
        srv.sendto(struct.pack("!12I", 0x1C000000, 0, 0, 0, 0, 0, 0, 0, seg, frac, seg, frac), cliente)

    threading.Thread(target=responder, daemon=True).start()
    try:
        desfase = hora.consultar_ntp("127.0.0.1", puerto=puerto)
    finally:
        srv.close()
    assert 1300 < desfase < 1700
