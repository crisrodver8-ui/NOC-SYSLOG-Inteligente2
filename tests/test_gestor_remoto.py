"""
Pruebas del GESTOR SSH/consola contra un equipo virtual real (tools/equipo_virtual.py):
conexión SSH con paramiko, consola telnet tipo GNS3, lista de hosts, lista de comandos,
ejecución de una acción aprobada y lectura de puertos.
"""
import os
import sys

import pytest

from conftest import cab

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
equipo_virtual = pytest.importorskip("equipo_virtual")
pytest.importorskip("paramiko")

USUARIO, CLAVE = "noc", "LabNoc2026x"


@pytest.fixture(scope="module")
def puertos():
    return {"ssh": equipo_virtual.iniciar_ssh(puerto=0, usuario=USUARIO, clave=CLAVE),
            "telnet": equipo_virtual.iniciar_telnet(puerto=0, usuario=USUARIO, clave=CLAVE)}


@pytest.fixture
def app_real(app, puertos):
    app.config.update(SSH_USUARIO=USUARIO, SSH_CLAVE=CLAVE, SSH_TIMEOUT_S=3)
    return app


def _equipo(cliente, gestion, puertos, nombre="R-VIRTUAL", ip="127.0.0.2"):
    datos = {"nombre": nombre, "ip": ip, "marca": "Cisco", "modelo": "IOSv", "simulado": False, "autorizado": True,
             "gestion": gestion, "ssh_puerto": puertos["ssh"], "consola_tipo": "telnet",
             "consola_destino": f"127.0.0.1:{puertos['telnet']}"}
    if gestion == "ssh":
        datos["ip"] = "127.0.0.1"
    r = cliente.post("/api/dispositivos", headers=cab(), json=datos)
    assert r.status_code == 201, r.json
    return r.json["id"]


def test_ssh_consulta_real(app_real, puertos):
    c = app_real.test_client()
    # 127.0.0.1 ya existe en la semilla (LAB-LOCALHOST): se reutiliza convirtiéndolo en equipo real
    lab = next(d for d in c.get("/api/dispositivos", headers=cab()).json if d["ip"] == "127.0.0.1")
    c.put(f"/api/dispositivos/{lab['id']}", headers=cab(), json={**lab, "marca": "Cisco", "simulado": False,
                                                                 "gestion": "ssh", "ssh_puerto": puertos["ssh"]})
    r = c.post("/api/consola", headers=cab(), json={"dispositivo_id": lab["id"], "comando": "show clock"})
    assert r.json["permitido"] and r.json["modo"] == "real"
    assert "COT" in r.json["salida"]
    # Comando peligroso: se bloquea ANTES de conectarse
    r = c.post("/api/consola", headers=cab(), json={"dispositivo_id": lab["id"], "comando": "configure terminal"})
    assert r.json["permitido"] is False and "BLOQUEADO" in r.json["salida"]


def test_consola_telnet_gns3_y_sincronizar_puertos(app_real, puertos):
    c = app_real.test_client()
    did = _equipo(c, "consola", puertos)
    assert c.post(f"/api/dispositivos/{did}/probar", headers=cab(), json={}).json["ok"] is True
    r = c.post(f"/api/dispositivos/{did}/interfaces/sincronizar", headers=cab(), json={})
    assert r.status_code == 200 and r.json["leidos"] == 4
    puertos_eq = {p["nombre"]: p["estado"] for p in c.get(f"/api/dispositivos/{did}", headers=cab()).json["interfaces"]}
    assert puertos_eq["GigabitEthernet0/0"] == "up" and puertos_eq["GigabitEthernet0/1"] == "admin_down"


def test_lista_de_hosts_de_consola(app_real, puertos):
    c = app_real.test_client()
    app_real.config["CONSOLA_HOSTS_PERMITIDOS"] = ["10.9.9.9"]
    did = _equipo(c, "consola", puertos)
    r = c.post(f"/api/dispositivos/{did}/probar", headers=cab(), json={})
    assert r.json["ok"] is False and "CONSOLA_HOSTS_PERMITIDOS" in r.json["detalle"]


def test_equipo_no_autorizado_no_se_conecta(app_real, puertos):
    c = app_real.test_client()
    did = _equipo(c, "consola", puertos)
    d = c.get(f"/api/dispositivos/{did}", headers=cab()).json
    c.put(f"/api/dispositivos/{did}", headers=cab(), json={**d, "autorizado": False})
    r = c.post("/api/consola", headers=cab(), json={"dispositivo_id": did, "comando": "show clock"})
    assert r.json["permitido"] is False


def test_accion_aprobada_se_ejecuta_en_el_equipo(app_real, puertos):
    c = app_real.test_client()
    did = _equipo(c, "consola", puertos)
    aid = c.post("/api/acciones", headers=cab(), json={"dispositivo_id": did, "tipo": "bloquear_ip",
                                                       "parametro": "203.0.113.66", "justificacion": "IP atacante en logs"}).json["id"]
    c.post(f"/api/acciones/{aid}/revisar", headers=cab("supervisor1"), json={"decision": "aprobar"})
    r = c.post(f"/api/acciones/{aid}/ejecutar", headers=cab(), json={})
    assert r.status_code == 200 and r.json["resultado"].startswith("[REAL]")
    assert "deny ip host 203.0.113.66" in r.json["resultado"]
    # El equipo guardó la configuración: se comprueba con un comando de consulta
    log_cfg = c.post("/api/consola", headers=cab(), json={"dispositivo_id": did, "comando": "show archive log config all"})
    assert "203.0.113.66" in log_cfg.json["salida"]


def test_clave_incorrecta(app_real, puertos):
    app_real.config["SSH_CLAVE"] = "ClaveMala12345"
    c = app_real.test_client()
    did = _equipo(c, "consola", puertos)
    assert c.post(f"/api/dispositivos/{did}/probar", headers=cab(), json={}).json["ok"] is False


def test_credenciales_nunca_se_devuelven(app_real, puertos):
    c = app_real.test_client()
    did = _equipo(c, "consola", puertos)
    r = c.get(f"/api/dispositivos/{did}", headers=cab())
    assert CLAVE not in r.get_data(as_text=True) and r.json["credenciales_configuradas"] is True
