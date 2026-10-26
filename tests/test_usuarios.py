"""Pruebas de SEGURIDAD: usuarios, claves, sesiones, roles, CSRF y tokens de la API (hallazgos del Corte 2)."""
from conftest import CLAVE_PRUEBA, cab

CSRF = {"X-NOC": "1"}


def login(cliente, usuario, clave=CLAVE_PRUEBA):
    return cliente.post("/api/sesion/login", json={"usuario": usuario, "clave": clave})


def test_configuracion_inicial_solo_una_vez(cliente):
    r = cliente.post("/api/sesion/inicial", json={"usuario": "otro", "clave": "OtraClave2026x"})
    assert r.status_code == 403   # ya existen usuarios


def test_login_y_logout(cliente):
    assert login(cliente, "operador1").status_code == 200
    assert cliente.get("/api/sesion").json["autenticado"] is True
    assert cliente.get("/api/dispositivos").status_code == 200
    cliente.post("/api/sesion/logout")
    assert cliente.get("/api/dispositivos").status_code == 401


def test_clave_incorrecta_mensaje_generico(cliente):
    r1 = login(cliente, "operador1", "Incorrecta123")
    r2 = login(cliente, "noexiste", "Incorrecta123")
    assert r1.status_code == r2.status_code == 401
    assert r1.json["error"] == r2.json["error"]  # no revela si el usuario existe


def test_bloqueo_por_intentos(cliente):
    for _ in range(5):
        login(cliente, "operador2", "Incorrecta123")
    r = login(cliente, "operador2")   # aun con la clave correcta
    assert r.status_code == 401 and "bloqueada" in r.json["error"]


def test_admin_crea_auditor_con_clave_temporal(cliente):
    r = cliente.post("/api/usuarios", headers=cab("admin"), json={"usuario": "auditor.externo", "nombre": "Auditor", "rol": "auditor"})
    assert r.status_code == 201
    temporal = r.json["clave_temporal"]
    # Con clave temporal solo puede cambiar la clave
    assert login(cliente, "auditor.externo", temporal).json["usuario"]["debe_cambiar_clave"] is True
    assert cliente.get("/api/auditoria").status_code == 403
    assert cliente.post("/api/sesion/clave", headers=CSRF, json={"actual": temporal, "nueva": "corta"}).status_code == 400
    assert cliente.post("/api/sesion/clave", headers=CSRF, json={"actual": temporal, "nueva": "AuditoriaSegura2026"}).status_code == 200
    # Ya puede auditar, pero no modificar nada
    assert cliente.get("/api/auditoria").status_code == 200
    assert cliente.get("/api/integridad").json["integra"] is True
    assert cliente.post("/api/simulador", headers=CSRF, json={}).status_code == 403
    assert cliente.post("/api/dispositivos", headers=CSRF, json={"nombre": "X1", "ip": "192.0.2.9", "marca": "Cisco"}).status_code == 403


def test_solo_admin_gestiona_usuarios(cliente):
    for u in ("supervisor1", "operador1", "auditor1"):
        assert cliente.get("/api/usuarios", headers=cab(u)).status_code == 403
        assert cliente.post("/api/usuarios", headers=cab(u), json={"usuario": "x.y", "rol": "admin"}).status_code == 403
    assert cliente.get("/api/usuarios", headers=cab("admin")).status_code == 200


def test_no_queda_sin_administrador(cliente):
    lista = cliente.get("/api/usuarios", headers=cab("admin")).json
    admin_id = next(u["id"] for u in lista if u["usuario"] == "admin")
    r = cliente.patch(f"/api/usuarios/{admin_id}", headers=cab("admin"), json={"rol": "operador"})
    assert r.status_code == 400


def test_proteccion_csrf(cliente):
    login(cliente, "operador1")
    sin = cliente.post("/api/incidentes", json={"titulo": "Prueba CSRF", "severidad": 4})
    con = cliente.post("/api/incidentes", headers=CSRF, json={"titulo": "Prueba CSRF", "severidad": 4})
    assert sin.status_code == 403 and con.status_code == 201


def test_token_api_crear_usar_revocar(cliente):
    login(cliente, "operador1")
    token = cliente.post("/api/tokens", headers=CSRF, json={"nombre": "script", "dias": 30}).json["token"]
    assert token.startswith("noc_")
    otro = cliente.application.test_client()
    assert otro.get("/api/eventos", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    tid = cliente.get("/api/tokens").json[0]["id"]
    cliente.delete(f"/api/tokens/{tid}", headers=CSRF)
    assert otro.get("/api/eventos", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_usuario_desactivado_pierde_acceso(cliente):
    lista = cliente.get("/api/usuarios", headers=cab("admin")).json
    uid = next(u["id"] for u in lista if u["usuario"] == "operador2")
    cliente.patch(f"/api/usuarios/{uid}", headers=cab("admin"), json={"activo": False})
    assert cliente.get("/api/eventos", headers=cab("operador2")).status_code == 401
    assert login(cliente, "operador2").status_code == 401


def test_politica_de_claves():
    from noc.autenticacion import ErrorAutenticacion, validar_clave
    for mala in ("corta1", "sololetrasmuylarga", "1234567890123", "operador1Clave99"):
        try:
            validar_clave(mala, "operador1")
            raise AssertionError(f"debió rechazar {mala}")
        except ErrorAutenticacion:
            pass
    validar_clave("ClaveBuena2026", "operador1")


def test_auditoria_registra_logins(cliente):
    login(cliente, "operador1", "Mala12345678")
    login(cliente, "operador1")
    acciones = [a["accion"] for a in cliente.get("/api/auditoria", headers=cab("auditor1")).json]
    assert "login_fallido" in acciones and "login" in acciones


def test_indice_api_publico(cliente):
    r = cliente.get("/api/")
    rutas = [x["ruta"] for x in r.json["rutas"]]
    assert "/api/eventos" in rutas and "/api/tokens" in rutas
