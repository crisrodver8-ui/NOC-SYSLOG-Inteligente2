"""
Resumen del panel, configuraciones, consola (simulada o real), política,
verificación de políticas, hora NTP, integridad, Telegram, auditoría e índice de la API.
"""
import glob
import os
from datetime import datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from .. import consola, generador_config, gestor_remoto, hora, politica, receptor_udp
from ..db import filas, get_db, registrar_auditoria, verificar_cadena
from ..notificador import enmascarar
from . import ErrorAPI, cuerpo_json, requiere

bp = Blueprint("herramientas", __name__)


def _hace(**kw) -> str:
    return (datetime.now() - timedelta(**kw)).isoformat(timespec="seconds")


# --------------------------------------------------------------- públicos
@bp.get("/estado")
def estado():
    """Estado general: versión, receptor, hora del servidor y verificación NTP (sin datos sensibles)."""
    return jsonify(version=current_app.config["VERSION"], receptor=receptor_udp.estado,
                   hora=datetime.now().isoformat(timespec="seconds"), ntp=hora.estado)


@bp.get("/")
def indice_api():
    """Índice de la API REST: lista de rutas, métodos y descripción."""
    rutas = []
    for regla in current_app.url_map.iter_rules():
        if not regla.rule.startswith("/api"):
            continue
        vista = current_app.view_functions[regla.endpoint]
        doc = (vista.__doc__ or "").strip().split("\n")[0]
        rutas.append({"ruta": regla.rule, "metodos": sorted(regla.methods - {"HEAD", "OPTIONS"}), "descripcion": doc})
    return jsonify(version=current_app.config["VERSION"], autenticacion="Authorization: Bearer <token> (crear en la vista API)",
                   rutas=sorted(rutas, key=lambda r: r["ruta"]))


# ------------------------------------------------------------------ panel
@bp.get("/resumen")
@requiere()
def resumen():
    """Datos del panel general (KPIs, gráficos, salud de equipos, alertas e incidentes)."""
    db = get_db()
    h24, h1 = _hace(hours=24), _hace(hours=1)
    uno = lambda sql, *p: db.execute(sql, p).fetchone()[0]

    equipos = {r["estado"]: r["n"] for r in db.execute("SELECT estado, COUNT(*) n FROM dispositivos GROUP BY estado")}
    kpis = {
        "equipos": sum(equipos.values()), "equipos_por_estado": equipos,
        "no_autorizados": uno("SELECT COUNT(DISTINCT ip_origen) FROM eventos WHERE banderas LIKE '%fuente_no_autorizada%' AND recibido_en >= ?", h24),
        "eventos_24h": uno("SELECT COUNT(*) FROM eventos WHERE recibido_en >= ?", h24),
        "mensajes_24h": uno("SELECT COALESCE(SUM(repeticiones),0) FROM eventos WHERE recibido_en >= ?", h24),
        "eventos_1h": uno("SELECT COUNT(*) FROM eventos WHERE recibido_en >= ?", h1),
        "criticos_24h": uno("SELECT COUNT(*) FROM eventos WHERE severidad <= 3 AND recibido_en >= ?", h24),
        "sospechosos_24h": uno("SELECT COUNT(*) FROM eventos WHERE sospechoso = 1 AND recibido_en >= ?", h24),
        "riesgo_alto_24h": uno("SELECT COUNT(*) FROM eventos WHERE riesgo >= 60 AND recibido_en >= ?", h24),
        "incidentes_activos": uno("SELECT COUNT(*) FROM incidentes WHERE estado IN ('abierto','en_progreso')"),
        "incidentes_total": uno("SELECT COUNT(*) FROM incidentes"),
        "acciones_pendientes": uno("SELECT COUNT(*) FROM acciones WHERE estado = 'propuesta'"),
    }
    por_sev = {r["severidad"]: r["n"] for r in db.execute(
        "SELECT severidad, COUNT(*) n FROM eventos WHERE recibido_en >= ? GROUP BY severidad", (h24,))}
    por_hora = []
    base = datetime.now().replace(minute=0, second=0, microsecond=0)
    for i in range(11, -1, -1):
        ini = base - timedelta(hours=i)
        n = uno("SELECT COUNT(*) FROM eventos WHERE recibido_en >= ? AND recibido_en < ?",
                ini.isoformat(), (ini + timedelta(hours=1)).isoformat())
        por_hora.append({"hora": ini.strftime("%H:00"), "n": n})
    equipos_estado = filas(db.execute(
        """SELECT d.id, d.nombre, d.ip, d.marca, d.estado, d.autorizado, d.simulado,
                  COUNT(e.id) AS eventos,
                  SUM(CASE WHEN e.severidad <= 3 THEN 1 ELSE 0 END) AS criticos,
                  SUM(CASE WHEN e.sospechoso = 1 THEN 1 ELSE 0 END) AS sospechosos,
                  MAX(e.recibido_en) AS ultimo,
                  (SELECT COUNT(*) FROM interfaces i WHERE i.dispositivo_id = d.id AND i.estado = 'down') AS puertos_down
           FROM dispositivos d LEFT JOIN eventos e ON e.dispositivo_id = d.id AND e.recibido_en >= ?
           GROUP BY d.id ORDER BY criticos DESC, d.nombre""", (h24,)))
    criticos = filas(db.execute(
        """SELECT e.id, e.recibido_en, e.severidad, e.mensaje, e.ip_origen, e.sospechoso, e.banderas, e.riesgo,
                  COALESCE(d.nombre, e.hostname, e.ip_origen) AS equipo
           FROM eventos e LEFT JOIN dispositivos d ON d.id = e.dispositivo_id
           WHERE e.severidad <= 3 OR e.sospechoso = 1 ORDER BY e.id DESC LIMIT 8"""))
    incidentes = filas(db.execute(
        "SELECT id, titulo, severidad, estado, asignado_a, actualizado_en FROM incidentes "
        "WHERE estado IN ('abierto','en_progreso') ORDER BY severidad, id DESC LIMIT 6"))
    return jsonify(kpis=kpis, por_severidad=por_sev, por_hora=por_hora, equipos=equipos_estado,
                   criticos=criticos, incidentes=incidentes)


# -------------------------------------------------------- configuraciones
@bp.post("/configuraciones")
@requiere()
def generar_configuracion():
    """Genera la configuración Syslog comentada de un fabricante."""
    try:
        texto = generador_config.generar(cuerpo_json())
    except generador_config.ErrorValidacion as e:
        raise ErrorAPI(str(e))
    return jsonify(texto=texto)


# ---------------------------------------------------------------- consola
@bp.get("/consola/comandos")
@requiere()
def comandos_permitidos():
    """Lista de comandos de consulta permitidos por fabricante."""
    return jsonify(consola.PERMITIDOS)


@bp.post("/consola")
@requiere("operador")
def ejecutar_consola():
    """Ejecuta un comando de consulta: simulado o real (SSH/consola) según el equipo."""
    d = cuerpo_json()
    db = get_db()
    disp = db.execute("SELECT * FROM dispositivos WHERE id = ?", (d.get("dispositivo_id"),)).fetchone()
    if not disp:
        raise ErrorAPI("Selecciona un equipo.")
    disp = dict(disp)
    comando = consola.normalizar(d.get("comando", ""))
    if not disp["autorizado"]:
        permitido, motivo = False, "BLOQUEADO: el equipo no está en la lista permitida."
    else:
        permitido, motivo = consola.validar(disp["marca"], comando)
    modo = "simulado" if disp["simulado"] else "real"
    if not permitido:
        salida = motivo
    elif disp["simulado"]:
        salida = consola.salida_simulada(disp, comando)
    else:
        try:
            salida = gestor_remoto.ejecutar_consulta(current_app.config, disp, comando) or "(sin salida)"
        except gestor_remoto.ErrorGestion as e:
            permitido, salida, motivo = False, f"ERROR DE CONEXIÓN: {e}", str(e)
    registrar_auditoria(db, g.usuario, g.rol, "consola_permitido" if permitido else "consola_bloqueado",
                        disp["nombre"], f"[{modo}] {comando[:120]} -> {motivo[:200]}")
    return jsonify(permitido=permitido, motivo=motivo, salida=salida, modo=modo, prompt=f"{disp['nombre']}#")


# ---------------------------------------------------------------- política
@bp.get("/politica")
@requiere()
def ver_politica():
    """Parámetros y contadores de la política de defensa frente a agentes de IA."""
    cfg = current_app.config
    db = get_db()
    conteo = {b: db.execute("SELECT COUNT(*) FROM eventos WHERE banderas LIKE ?", (f"%{b}%",)).fetchone()[0]
              for b in ("fuente_no_autorizada", "posible_inyeccion", "ofuscacion", "fuerza_bruta", "cambio_no_autorizado",
                        "rafaga_cambios", "fuera_de_horario", "hora_desfasada", "cuenta_servicio", "cambio_config",
                        "fallo_autenticacion", "tormenta")}
    ingestor = current_app.extensions["ingestor"]
    return jsonify(
        parametros={
            "Ventana de deduplicación": f"{cfg['DEDUP_VENTANA_S']} s",
            "Límite por fuente (control de tormentas)": f"{cfg['LIMITE_MENSAJES_MIN']} mensajes/min",
            "Horario laboral": f"{cfg['HORARIO_INICIO']:02d}:00 - {cfg['HORARIO_FIN']:02d}:00, lunes a viernes",
            "Desfase máximo de hora del equipo": f"{cfg['DESFASE_MAX_S']} s",
            "Ráfaga de cambios": f"{cfg['RAFAGA_CAMBIOS']} cambios de configuración en 60 s",
            "Cambio autorizado": f"requiere acción aprobada en los últimos {cfg['VENTANA_CAMBIO_AUTORIZADO_MIN']} min",
            "Incidente automático": f"severidad 0 a {cfg['SEVERIDAD_AUTO_INCIDENTE']}, inyección, fuerza bruta, cambio no autorizado o ráfaga",
            "Fuerza bruta": f"{cfg['INTENTOS_FUERZA_BRUTA']} fallos de login en 5 min",
            "Alerta Telegram": f"severidad 0 a {cfg['TELEGRAM_SEVERIDAD_MAX']} o riesgo ≥ 60 (máx. {cfg['TELEGRAM_LIMITE_MIN']}/min)",
            "Fuentes autorizadas": f"{db.execute('SELECT COUNT(*) FROM dispositivos WHERE autorizado=1').fetchone()[0]} equipos en lista permitida",
        },
        banderas=conteo,
        contadores=ingestor.contadores,
        descartados_por_ip=dict(ingestor.limitador.descartados),
        acciones={r["estado"]: r["n"] for r in db.execute("SELECT estado, COUNT(*) n FROM acciones GROUP BY estado")},
    )


@bp.get("/verificacion")
@requiere()
def verificacion():
    """Verificación de políticas Syslog por equipo y controles globales del sistema."""
    cfg = current_app.config
    db = get_db()
    h24 = _hace(hours=24)
    equipos = []
    for d in db.execute("SELECT * FROM dispositivos ORDER BY nombre").fetchall():
        ult = db.execute("""SELECT recibido_en, desfase_s FROM eventos WHERE dispositivo_id = ? AND origen != 'politica'
                            ORDER BY id DESC LIMIT 1""", (d["id"],)).fetchone()
        ult_desfase = db.execute("""SELECT desfase_s FROM eventos WHERE dispositivo_id = ? AND desfase_s IS NOT NULL
                                    ORDER BY id DESC LIMIT 1""", (d["id"],)).fetchone()
        puertos = db.execute("SELECT COUNT(*) FROM interfaces WHERE dispositivo_id = ?", (d["id"],)).fetchone()[0]
        chequeos = {
            "Lista permitida": ("ok", "Autorizado") if d["autorizado"] else ("fallo", "No autorizado: sus eventos se marcan"),
            "Envía Syslog (24 h)": ("ok", f"Último: {ult['recibido_en'][11:19]}") if ult and ult["recibido_en"] >= h24
            else ("fallo" if d["estado"] == "activo" else "sin_datos", "Sin eventos en 24 h"),
            "Hora sincronizada (NTP)": ("sin_datos", "Sin eventos con fecha") if not ult_desfase
            else (("ok", f"Desfase {ult_desfase['desfase_s']} s") if abs(ult_desfase["desfase_s"]) <= cfg["DESFASE_MAX_S"]
                  else ("fallo", f"Desfase {ult_desfase['desfase_s']} s")),
            "Consola documentada": ("ok", f"{d['consola_tipo']} {d['consola_destino']}") if d["consola_tipo"] != "ninguna"
            else ("advertencia", "Sin puerto de consola registrado"),
            "Puertos registrados": ("ok", f"{puertos} puertos") if puertos else ("advertencia", "Sin puertos"),
            "Gestión remota": ("ok", "SSH") if d["gestion"] == "ssh"
            else ("advertencia", "Telnet de consola (solo laboratorio)") if d["gestion"] == "consola"
            else ("sin_datos", "Simulado" if d["simulado"] else "No habilitada"),
        }
        equipos.append({"id": d["id"], "nombre": d["nombre"], "simulado": d["simulado"],
                        "chequeos": {k: {"estado": v[0], "detalle": v[1]} for k, v in chequeos.items()}})

    cadena = verificar_cadena(db)
    triggers = db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0]
    respaldos = sorted(glob.glob(os.path.join(cfg["RESPALDOS_DIR"], "noc-*.db")))
    ultimo_respaldo = datetime.fromtimestamp(os.path.getmtime(respaldos[-1])).isoformat(timespec="seconds") if respaldos else None
    ntp = hora.estado
    globales = {
        "Receptor Syslog": ("ok", f"UDP {receptor_udp.estado['puerto']}") if receptor_udp.estado["activo"]
        else ("fallo", receptor_udp.estado.get("error") or "Apagado"),
        "Hora del servidor (NTP)": ("sin_datos", ntp.get("error") or "Aún no verificada") if not ntp["verificado"]
        else (("ok" if ntp["sincronizado"] else "fallo"), f"Desfase {ntp['desfase_ms']} ms con {ntp['servidor']}"),
        "Fechas inmutables": ("ok", f"{triggers} reglas de inmutabilidad activas") if triggers >= 10 else ("fallo", f"Solo {triggers} reglas"),
        "Integridad de la auditoría": ("ok", f"{cadena['total']} registros encadenados íntegros") if cadena["integra"]
        else ("fallo", f"Registro #{cadena['fila_alterada']} alterado"),
        "Alertas Telegram": ("ok", "Configurado") if current_app.extensions["notificador"].configurado
        else ("advertencia", "Sin configurar (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)"),
        "Respaldo (24 h)": ("ok", f"Último: {ultimo_respaldo}") if ultimo_respaldo and ultimo_respaldo >= h24
        else ("advertencia", "Sin respaldo reciente: python tools/respaldo.py"),
    }
    return jsonify(equipos=equipos, globales={k: {"estado": v[0], "detalle": v[1]} for k, v in globales.items()})


@bp.post("/hora/verificar")
@requiere("admin", "supervisor")
def verificar_hora():
    """Consulta el servidor NTP ahora y registra el resultado."""
    cfg = current_app.config
    r = hora.verificar(cfg["NTP_SERVIDOR"], cfg["NTP_DESFASE_MAX_MS"])
    registrar_auditoria(get_db(), g.usuario, g.rol, "verificar_hora_ntp", cfg["NTP_SERVIDOR"],
                        f"desfase {r['desfase_ms']} ms" if r["verificado"] else r["error"])
    return jsonify(r)


@bp.get("/integridad")
@requiere("supervisor", "auditor")
def integridad():
    """Recalcula la cadena de hashes de la auditoría."""
    db = get_db()
    r = verificar_cadena(db)
    registrar_auditoria(db, g.usuario, g.rol, "verificar_integridad", "auditoría",
                        "íntegra" if r["integra"] else f"ALTERADA en #{r['fila_alterada']}")
    return jsonify(r)


# ---------------------------------------------------------------- Telegram
@bp.get("/telegram")
@requiere("supervisor", "auditor")
def estado_telegram():
    """Estado de las alertas Telegram (el token se muestra enmascarado)."""
    n = current_app.extensions["notificador"]
    cfg = current_app.config
    return jsonify(configurado=n.configurado, token=enmascarar(cfg["TELEGRAM_TOKEN"]),
                   chat_id=("…" + cfg["TELEGRAM_CHAT_ID"][-4:]) if cfg["TELEGRAM_CHAT_ID"] else "",
                   estadisticas=n.estadisticas,
                   historial=filas(get_db().execute("SELECT * FROM notificaciones ORDER BY id DESC LIMIT 20")))


@bp.post("/telegram/prueba")
@requiere("admin")
def prueba_telegram():
    """Envía un mensaje de prueba al chat configurado."""
    ok, detalle = current_app.extensions["notificador"].enviar_ahora(
        "✅ Prueba del NOC Syslog Inteligente", f"Mensaje de prueba enviado por {g.usuario}.")
    registrar_auditoria(get_db(), g.usuario, g.rol, "telegram_prueba", "", detalle)
    if not ok:
        raise ErrorAPI(detalle, 502)
    return jsonify(ok=True, detalle=detalle)


# ---------------------------------------------------------------- auditoría
@bp.get("/auditoria")
@requiere("supervisor", "auditor")
def auditoria():
    """Registros de auditoría (más recientes primero)."""
    try:
        limite = min(int(request.args.get("limite", 200)), 1000)
    except ValueError:
        raise ErrorAPI("Límite inválido.")
    return jsonify(filas(get_db().execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,))))
