"""Pruebas funcionales de la API (flujo de extremo a extremo)."""
from conftest import cab


def test_requiere_usuario(cliente):
    assert cliente.get("/api/dispositivos").status_code == 401
    assert cliente.get("/api/dispositivos", headers={"Authorization": "Bearer noc_falso"}).status_code == 401
    assert cliente.get("/api/dispositivos", headers={"X-Usuario": "operador1"}).status_code == 401  # v0.2.0 ya no sirve


def test_inventario_crud(cliente):
    r = cliente.post("/api/dispositivos", headers=cab(), json={
        "nombre": "PRUEBA-SW", "ip": "192.0.2.77", "marca": "Cisco", "modelo": "C9200", "estado": "activo"})
    assert r.status_code == 201
    id_ = r.json["id"]
    assert cliente.post("/api/dispositivos", headers=cab(), json={
        "nombre": "OTRO", "ip": "192.0.2.77", "marca": "Cisco"}).status_code == 409   # IP duplicada
    assert cliente.post("/api/dispositivos", headers=cab(), json={
        "nombre": "MAL", "ip": "999.1.1.1", "marca": "Cisco"}).status_code == 400     # IP inválida
    assert cliente.put(f"/api/dispositivos/{id_}", headers=cab(), json={
        "nombre": "PRUEBA-SW", "ip": "192.0.2.77", "marca": "Cisco", "estado": "mantenimiento"}).status_code == 200
    assert cliente.delete(f"/api/dispositivos/{id_}", headers=cab()).status_code == 403  # operador no borra
    assert cliente.delete(f"/api/dispositivos/{id_}", headers=cab("supervisor1")).status_code == 200


def test_auditor_no_modifica(cliente):
    assert cliente.post("/api/simulador", headers=cab("auditor1"), json={}).status_code == 403


def test_ingesta_fuente_no_autorizada_y_deduplicacion(app):
    ingestor = app.extensions["ingestor"]
    from noc.db import connect
    conn = connect(app.config["DB_PATH"])
    r1 = ingestor.procesar(conn, "<187>Oct  9 10:00:00 X app: fallo", "203.0.113.250", "udp")
    assert "fuente_no_autorizada" in r1["banderas"]
    r2 = ingestor.procesar(conn, "<187>Oct  9 10:00:00 X app: fallo", "203.0.113.250", "udp")
    assert r2["estado"] == "duplicado"
    assert conn.execute("SELECT repeticiones FROM eventos WHERE id = ?", (r1["evento_id"],)).fetchone()[0] == 2


def test_importar_archivo(cliente):
    contenido = (b"<189>Oct  9 10:00:00 LAB-RT-BORDE01 %SYS-5-CONFIG_I: Configured from console by admin\n"
                 b"<190>Oct  9 10:00:05 LAB-SW-DIST01 test: informativo\n")
    import io
    r = cliente.post("/api/eventos/importar", headers=cab(),
                     data={"archivo": (io.BytesIO(contenido), "prueba.log")}, content_type="multipart/form-data")
    assert r.status_code == 200 and r.json["almacenado"] == 2
    eventos = cliente.get("/api/eventos?marca=Cisco", headers=cab()).json
    assert eventos["total"] == 1   # filtro por marca: el host se asoció al inventario


def test_simulador_ataque_crea_incidentes_y_sospechosos(cliente):
    r = cliente.post("/api/simulador", headers=cab(), json={"escenario": "ataque_ia"})
    assert r.status_code == 200
    sospechosos = cliente.get("/api/eventos?sospechoso=1", headers=cab()).json
    assert sospechosos["total"] >= 8
    titulos = [i["titulo"] for i in cliente.get("/api/incidentes", headers=cab()).json]
    assert any("inyección" in t for t in titulos) and any("Fuerza bruta" in t for t in titulos)


def test_tormenta_descarta_mensajes(cliente):
    r = cliente.post("/api/simulador", headers=cab(), json={"escenario": "tormenta"}).json
    assert r["resultado"].get("descartado_tormenta", 0) > 0


def test_filtro_por_severidad(cliente):
    cliente.post("/api/simulador", headers=cab(), json={"escenario": "normal", "cantidad": 40})
    items = cliente.get("/api/eventos?severidad=4", headers=cab()).json["items"]
    assert all(e["severidad"] == 4 for e in items)


def test_ciclo_de_incidente(cliente):
    id_ = cliente.post("/api/incidentes", headers=cab(), json={"titulo": "Caída de enlace", "severidad": 3}).json["id"]
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(), json={"asignado_a": "operador2"}).status_code == 200
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(), json={"estado": "resuelto"}).status_code == 400  # salto inválido
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(), json={"estado": "en_progreso"}).status_code == 200
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(), json={"estado": "resuelto"}).status_code == 400  # falta solución
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(),
                         json={"estado": "resuelto", "solucion": "Se cambió el cable"}).status_code == 200
    assert cliente.patch(f"/api/incidentes/{id_}", headers=cab(), json={"estado": "cerrado"}).status_code == 200
    det = cliente.get(f"/api/incidentes/{id_}", headers=cab()).json
    assert det["incidente"]["estado"] == "cerrado" and len(det["notas"]) >= 4


def test_flujo_seguro_de_acciones(cliente):
    base = {"dispositivo_id": 1, "tipo": "bloquear_ip", "parametro": "203.0.113.66",
            "justificacion": "IP atacante detectada en los logs"}
    id_ = cliente.post("/api/acciones", headers=cab(), json=base).json["id"]
    # No se ejecuta sin aprobación
    assert cliente.post(f"/api/acciones/{id_}/ejecutar", headers=cab(), json={}).status_code == 403
    # Un operador no aprueba
    assert cliente.post(f"/api/acciones/{id_}/revisar", headers=cab(), json={"decision": "aprobar"}).status_code == 403
    # Quien propone no aprueba su propia acción
    id2 = cliente.post("/api/acciones", headers=cab("supervisor1"), json=base).json["id"]
    assert cliente.post(f"/api/acciones/{id2}/revisar", headers=cab("supervisor1"), json={"decision": "aprobar"}).status_code == 403
    # Flujo completo
    assert cliente.post(f"/api/acciones/{id_}/revisar", headers=cab("supervisor1"), json={"decision": "aprobar"}).status_code == 200
    assert cliente.post(f"/api/acciones/{id_}/ejecutar", headers=cab(), json={}).status_code == 200
    assert cliente.post(f"/api/acciones/{id_}/verificar", headers=cab(),
                        json={"verificacion": "La IP ya no aparece en los logs", "exito": True}).status_code == 200
    acciones_auditadas = [a["accion"] for a in cliente.get("/api/auditoria", headers=cab("auditor1")).json]
    for paso in ("proponer_accion", "accion_aprobada", "ejecutar_accion", "verificar_accion"):
        assert paso in acciones_auditadas


def test_accion_con_parametro_malicioso(cliente):
    r = cliente.post("/api/acciones", headers=cab(), json={
        "dispositivo_id": 1, "tipo": "bloquear_ip", "parametro": "1.1.1.1\nreload", "justificacion": "prueba de seguridad"})
    assert r.status_code == 400


def test_consola_bloquea_y_audita(cliente):
    r = cliente.post("/api/consola", headers=cab(), json={"dispositivo_id": 1, "comando": "write erase"})
    assert r.status_code == 200 and r.json["permitido"] is False
    r = cliente.post("/api/consola", headers=cab(), json={"dispositivo_id": 1, "comando": "show clock"})
    assert r.json["permitido"] is True and "SIMULADA" in r.json["salida"]
    auditoria = cliente.get("/api/auditoria", headers=cab("supervisor1")).json
    assert any(a["accion"] == "consola_bloqueado" for a in auditoria)


def test_generador_configuraciones(cliente):
    for marca, esperado in (("Cisco", "logging host 198.51.100.200"), ("Fortinet", 'set server "198.51.100.200"'),
                            ("Huawei", "info-center loghost 198.51.100.200")):
        r = cliente.post("/api/configuraciones", headers=cab(), json={
            "marca": marca, "servidor": "198.51.100.200", "ntp": "198.51.100.123", "puerto": 514, "nivel": 6, "facility": 7})
        assert r.status_code == 200 and esperado in r.json["texto"]
    r = cliente.post("/api/configuraciones", headers=cab(), json={
        "marca": "Cisco", "servidor": "1.1.1.1\nreload", "ntp": "1.1.1.1"})
    assert r.status_code == 400
