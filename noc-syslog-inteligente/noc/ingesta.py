"""
Canal de ingesta: todo mensaje Syslog (UDP, archivo importado o simulador)
pasa por aquí en este orden:

  1. Control de tormentas (límite de mensajes por minuto por IP).
  2. Parseo (facility, severidad, fecha, host, mensaje).
  3. Identificación del equipo (lista permitida = inventario autorizado).
  4. Hora: se guarda la del colector (confiable) y se mide el desfase con la del equipo.
  5. Política: banderas, correlación con acciones aprobadas y puntaje de riesgo.
  6. Deduplicación (mismo mensaje dentro de la ventana = +1 repetición).
  7. Almacenamiento + actualización del estado de los puertos.
  8. Incidente automático y alerta por Telegram si corresponde.
"""
from datetime import datetime, timedelta

from . import interfaces, politica
from .db import ahora, registrar_auditoria
from .syslog_parser import SEVERIDADES, parsear

LARGO_MAXIMO = 4096  # bytes: mensajes más largos se recortan (evita abusos de memoria)
BANDERAS_INCIDENTE = {"posible_inyeccion", "fuerza_bruta", "cambio_no_autorizado", "rafaga_cambios"}


class Ingestor:
    def __init__(self, cfg: dict, notificador=None):
        self.cfg = cfg
        self.notificador = notificador
        self.limitador = politica.LimitadorFrecuencia(cfg["LIMITE_MENSAJES_MIN"])
        self.contadores = {"recibidos": 0, "almacenados": 0, "duplicados": 0, "descartados": 0}

    # ------------------------------------------------------------------ API
    def procesar(self, conn, crudo: str, ip_origen: str, origen: str) -> dict:
        """Procesa un mensaje. Devuelve un resumen de lo que pasó con él."""
        crudo = (crudo or "").strip()[:LARGO_MAXIMO]
        if not crudo:
            return {"estado": "vacio"}
        self.contadores["recibidos"] += 1
        momento = datetime.now()          # hora del COLECTOR: la única confiable

        # 1. Control de tormentas (no aplica a archivos importados por un operador)
        if origen in ("udp", "simulador") and not self.limitador.permitir(ip_origen):
            self.contadores["descartados"] += 1
            if self.limitador.debe_alertar(ip_origen):
                self._evento_tormenta(conn, ip_origen)
            return {"estado": "descartado_tormenta"}

        # 2. Parseo
        msg = parsear(crudo)

        # 3. Equipo: SOLO la IP de origen autoriza (el hostname del mensaje se puede falsificar)
        disp = conn.execute("SELECT * FROM dispositivos WHERE ip = ?", (ip_origen,)).fetchone()
        if disp is None and origen == "importacion" and msg.hostname:
            disp = conn.execute("SELECT * FROM dispositivos WHERE lower(nombre) = lower(?)", (msg.hostname,)).fetchone()
            if disp:
                ip_origen = disp["ip"]

        # 4. Hora: el reloj del equipo es un dato NO confiable
        banderas: list[str] = []
        desfase = None
        fecha_ref = momento
        if msg.fecha_evento:
            fecha_equipo = datetime.fromisoformat(msg.fecha_evento)
            if origen == "importacion":
                fecha_ref = fecha_equipo      # logs históricos: se usa su propia fecha
            else:
                desfase = int((fecha_equipo - momento).total_seconds())
                if abs(desfase) > self.cfg["DESFASE_MAX_S"]:
                    banderas.append("hora_desfasada")   # y el horario se evalúa con la hora del colector
                else:
                    fecha_ref = fecha_equipo

        # 5. Política
        banderas += politica.analizar_texto(msg.mensaje, fecha_ref, self.cfg["HORARIO_INICIO"], self.cfg["HORARIO_FIN"])
        if disp is None or not disp["autorizado"]:
            banderas.insert(0, "fuente_no_autorizada")
        if "fallo_autenticacion" in banderas and self._contar(conn, ip_origen, "fallo_autenticacion", 300) + 1 >= self.cfg["INTENTOS_FUERZA_BRUTA"]:
            banderas.append("fuerza_bruta")
        if "cambio_config" in banderas and origen != "importacion":
            if self._contar(conn, ip_origen, "cambio_config", 60) + 1 >= self.cfg["RAFAGA_CAMBIOS"]:
                banderas.append("rafaga_cambios")
            if disp is not None and not self._accion_aprobada_reciente(conn, disp["id"]):
                banderas.append("cambio_no_autorizado")
        sospechoso = politica.es_sospechoso(banderas)
        riesgo = politica.puntaje_riesgo(banderas, msg.severidad)

        # 6. Deduplicación
        huella = politica.huella(ip_origen, msg.severidad, msg.app, msg.mensaje)
        limite = (momento - timedelta(seconds=self.cfg["DEDUP_VENTANA_S"])).isoformat(timespec="seconds")
        previo = conn.execute("SELECT id FROM eventos WHERE huella = ? AND ultima_vez >= ? ORDER BY id DESC LIMIT 1",
                              (huella, limite)).fetchone()
        if previo:
            conn.execute("UPDATE eventos SET repeticiones = repeticiones + 1, ultima_vez = ? WHERE id = ?",
                         (ahora(), previo["id"]))
            conn.commit()
            self.contadores["duplicados"] += 1
            return {"estado": "duplicado", "evento_id": previo["id"]}

        # 7. Almacenamiento
        marca = disp["marca"] if disp else msg.marca_detectada
        cur = conn.execute(
            """INSERT INTO eventos (recibido_en, fecha_evento, ip_origen, hostname, dispositivo_id, marca,
                   facility, facility_nombre, severidad, app, mensaje, crudo, formato, origen,
                   huella, repeticiones, ultima_vez, banderas, sospechoso, riesgo, desfase_s)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (momento.isoformat(timespec="seconds"), msg.fecha_evento, ip_origen,
             msg.hostname or (disp["nombre"] if disp else None), disp["id"] if disp else None, marca,
             msg.facility, msg.facility_nombre, msg.severidad, msg.app, msg.mensaje, crudo, msg.formato, origen,
             huella, ahora(), ",".join(banderas), int(sospechoso), riesgo, desfase))
        evento_id = cur.lastrowid
        self.contadores["almacenados"] += 1
        if disp is not None and disp["autorizado"]:
            self._actualizar_puerto(conn, disp["id"], msg.mensaje)

        # 8. Incidente automático y alerta
        incidente_id = None
        if msg.severidad <= self.cfg["SEVERIDAD_AUTO_INCIDENTE"] or BANDERAS_INCIDENTE & set(banderas):
            incidente_id = self._incidente_automatico(conn, evento_id, disp, ip_origen, msg, banderas)
        conn.commit()
        self._alertar(evento_id, disp, ip_origen, msg, banderas, riesgo, incidente_id)
        return {"estado": "almacenado", "evento_id": evento_id, "incidente_id": incidente_id,
                "severidad": msg.severidad, "banderas": banderas, "riesgo": riesgo}

    # ------------------------------------------------------------ auxiliares
    def _contar(self, conn, ip: str, bandera: str, segundos: int) -> int:
        """Eventos (con repeticiones) de la misma IP con esa bandera en la ventana indicada."""
        desde = (datetime.now() - timedelta(seconds=segundos)).isoformat(timespec="seconds")
        return conn.execute(
            """SELECT COALESCE(SUM(repeticiones), 0) FROM eventos
               WHERE ip_origen = ? AND ultima_vez >= ? AND banderas LIKE ?""",
            (ip, desde, f"%{bandera}%")).fetchone()[0]

    def _accion_aprobada_reciente(self, conn, dispositivo_id: int) -> bool:
        """¿Hay una acción aprobada/ejecutada para este equipo en los últimos N minutos?"""
        desde = (datetime.now() - timedelta(minutes=self.cfg["VENTANA_CAMBIO_AUTORIZADO_MIN"])).isoformat(timespec="seconds")
        return conn.execute(
            """SELECT 1 FROM acciones WHERE dispositivo_id = ? AND estado IN ('aprobada','ejecutada','verificada')
               AND actualizado_en >= ? LIMIT 1""", (dispositivo_id, desde)).fetchone() is not None

    def _actualizar_puerto(self, conn, dispositivo_id: int, mensaje: str):
        """Si el mensaje informa que un puerto subió o bajó, actualiza su estado."""
        cambio = interfaces.estado_desde_syslog(mensaje)
        if not cambio:
            return
        nombre, estado = cambio
        norm = interfaces.normalizar(nombre)
        fila = conn.execute("SELECT id FROM interfaces WHERE dispositivo_id = ? AND nombre_norm = ?",
                            (dispositivo_id, norm)).fetchone()
        if fila:
            conn.execute("UPDATE interfaces SET estado = ?, actualizado_en = ? WHERE id = ?", (estado, ahora(), fila["id"]))
        else:
            conn.execute(
                """INSERT INTO interfaces (dispositivo_id, nombre, nombre_norm, tipo, estado, origen, actualizado_en)
                   VALUES (?, ?, ?, 'cobre', ?, 'syslog', ?)""", (dispositivo_id, nombre[:60], norm, estado, ahora()))

    def _incidente_automatico(self, conn, evento_id, disp, ip, msg, banderas) -> int | None:
        """Crea un incidente o, si ya hay uno abierto parecido, le agrega una nota (evita duplicar)."""
        nombre = disp["nombre"] if disp else ip
        motivo = ("Posible inyección para IA" if "posible_inyeccion" in banderas else
                  "Cambio de configuración no autorizado" if "cambio_no_autorizado" in banderas else
                  "Ráfaga de cambios (ritmo de máquina)" if "rafaga_cambios" in banderas else
                  "Fuerza bruta" if "fuerza_bruta" in banderas else SEVERIDADES[msg.severidad])
        titulo = f"[AUTO] {motivo} en {nombre}"
        desde = (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds")
        abierto = conn.execute(
            """SELECT id FROM incidentes WHERE titulo = ? AND estado IN ('abierto','en_progreso')
               AND creado_en >= ? ORDER BY id DESC LIMIT 1""", (titulo, desde)).fetchone()
        if abierto:
            conn.execute("INSERT INTO incidente_notas (incidente_id, autor, nota, creado_en) VALUES (?, 'sistema', ?, ?)",
                         (abierto["id"], f"Evento relacionado #{evento_id} agregado automáticamente.", ahora()))
            return abierto["id"]
        cur = conn.execute(
            """INSERT INTO incidentes (titulo, descripcion, severidad, estado, creado_por, evento_id,
                   dispositivo_id, creado_en, actualizado_en)
               VALUES (?, ?, ?, 'abierto', 'sistema', ?, ?, ?, ?)""",
            (titulo, f"Creado por la política a partir del evento #{evento_id}. Banderas: {', '.join(banderas) or 'ninguna'}.",
             msg.severidad, evento_id, disp["id"] if disp else None, ahora(), ahora()))
        incidente_id = cur.lastrowid
        registrar_auditoria(conn, "sistema", "sistema", "incidente_automatico", f"incidente #{incidente_id}", titulo)
        if self.notificador:
            self.notificador.alertar(f"🚨 Nuevo incidente #{incidente_id}", [titulo, f"Evento #{evento_id}: {msg.mensaje[:200]}"],
                                     clave_dedup=titulo)
        return incidente_id

    def _alertar(self, evento_id, disp, ip, msg, banderas, riesgo, incidente_id):
        """Alerta Telegram por severidad o riesgo alto (si no se envió ya por el incidente)."""
        if not self.notificador or incidente_id:
            return
        if msg.severidad <= self.cfg["TELEGRAM_SEVERIDAD_MAX"] or riesgo >= 60:
            equipo = disp["nombre"] if disp else ip
            self.notificador.alertar(
                f"⚠️ {SEVERIDADES[msg.severidad]} en {equipo} (riesgo {riesgo})",
                [f"Evento #{evento_id}", f"Banderas: {', '.join(banderas) or 'ninguna'}", f"Mensaje: {msg.mensaje[:200]}"],
                clave_dedup=f"{ip}|{msg.app}|{msg.severidad}")

    def _evento_tormenta(self, conn, ip: str):
        """Registra UN evento de la propia política avisando la tormenta."""
        texto = (f"Control de tormentas: la fuente {ip} superó {self.limitador.limite} mensajes/minuto. "
                 f"Los mensajes excedentes se descartan.")
        disp = conn.execute("SELECT id, nombre, marca FROM dispositivos WHERE ip = ?", (ip,)).fetchone()
        conn.execute(
            """INSERT INTO eventos (recibido_en, fecha_evento, ip_origen, hostname, dispositivo_id, marca,
                   facility, facility_nombre, severidad, app, mensaje, crudo, formato, origen,
                   huella, repeticiones, ultima_vez, banderas, sospechoso, riesgo, desfase_s)
               VALUES (?, ?, ?, ?, ?, ?, 5, 'syslog', 4, 'NOC-POLITICA', ?, ?, 'interno', 'politica', ?, 1, ?, 'tormenta', 1, ?, 0)""",
            (ahora(), ahora(), ip, disp["nombre"] if disp else None, disp["id"] if disp else None,
             disp["marca"] if disp else None, texto, texto, politica.huella(ip, 4, "NOC", texto + ahora()), ahora(),
             politica.puntaje_riesgo(["tormenta"], 4)))
        registrar_auditoria(conn, "sistema", "sistema", "tormenta_detectada", ip, texto)
        conn.commit()
        if self.notificador:
            self.notificador.alertar("🌪 Tormenta de eventos", [texto], clave_dedup=f"tormenta|{ip}")
