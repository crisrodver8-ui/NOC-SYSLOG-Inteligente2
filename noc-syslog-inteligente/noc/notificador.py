"""
Alertas por Telegram.

- El token del bot y el chat se leen SOLO de .env (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID).
  Nunca se escriben en la BD, en los logs ni en la interfaz (allí se muestra enmascarado).
- Los envíos van a una cola y los hace un hilo aparte: si Telegram no responde,
  la recepción de Syslog no se detiene.
- Límite de envíos por minuto y deduplicación para no inundar el chat (anti-tormenta).
- El texto del log se envía como DATO: se recorta y se escapan los caracteres HTML.
"""
import html
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request
from collections import deque

from .db import ahora, connect

log = logging.getLogger("noc.telegram")


def enmascarar(token: str) -> str:
    return (token[:4] + "…" + token[-3:]) if len(token) > 10 else ("(configurado)" if token else "")


class NotificadorTelegram:
    def __init__(self, token: str, chat_id: str, db_path: str, limite_min: int = 20, enviar_fn=None):
        self.token, self.chat_id, self.db_path = token, chat_id, db_path
        self.limite_min = limite_min
        self._cola: queue.Queue = queue.Queue(maxsize=500)
        self._enviados: deque = deque()
        self._recientes: dict[str, float] = {}
        self._enviar_fn = enviar_fn or self._enviar_http   # se reemplaza en las pruebas
        self._hilo = None
        self.estadisticas = {"enviadas": 0, "errores": 0, "omitidas": 0}

    @property
    def configurado(self) -> bool:
        return bool(self.token and self.chat_id)

    def iniciar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True, name="telegram")
            self._hilo.start()

    # ------------------------------------------------------------ API pública
    def alertar(self, asunto: str, lineas: list[str], clave_dedup: str | None = None) -> bool:
        """Encola una alerta. Devuelve False si se omitió (no configurado, duplicada o límite)."""
        if not self.configurado:
            return False
        ahora_s = time.monotonic()
        clave = clave_dedup or asunto
        if ahora_s - self._recientes.get(clave, -1e9) < 300:   # misma alerta en 5 min: se omite
            self.estadisticas["omitidas"] += 1
            return False
        self._recientes[clave] = ahora_s
        texto = f"<b>{html.escape(asunto)}</b>\n" + "\n".join(html.escape(l)[:300] for l in lineas)
        try:
            self._cola.put_nowait((asunto, texto[:3500]))
            return True
        except queue.Full:
            self.estadisticas["omitidas"] += 1
            return False

    def enviar_ahora(self, asunto: str, texto: str) -> tuple[bool, str]:
        """Envío síncrono (botón «Enviar prueba»)."""
        if not self.configurado:
            return False, "Telegram no está configurado (faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en .env)."
        ok, detalle = self._enviar_fn(f"<b>{html.escape(asunto)}</b>\n{html.escape(texto)}")
        self._registrar(asunto, ok, detalle)
        return ok, detalle

    # -------------------------------------------------------------- interno
    def _bucle(self):
        while True:
            asunto, texto = self._cola.get()
            # Límite de envíos por minuto
            while self._enviados and time.monotonic() - self._enviados[0] > 60:
                self._enviados.popleft()
            if len(self._enviados) >= self.limite_min:
                self.estadisticas["omitidas"] += 1
                self._registrar(asunto, None, "Límite de alertas por minuto alcanzado")
                continue
            self._enviados.append(time.monotonic())
            ok, detalle = self._enviar_fn(texto)
            self._registrar(asunto, ok, detalle)

    def _enviar_http(self, texto: str) -> tuple[bool, str]:
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        datos = json.dumps({"chat_id": self.chat_id, "text": texto, "parse_mode": "HTML",
                            "disable_web_page_preview": True}).encode()
        try:
            req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status == 200, "Enviada"
        except urllib.error.HTTPError as e:
            # Nunca se registra la URL (contiene el token)
            return False, f"Telegram respondió HTTP {e.code}"
        except OSError as e:
            return False, f"Sin conexión con Telegram ({e.__class__.__name__})"

    def _registrar(self, asunto: str, ok: bool | None, detalle: str):
        estado = "omitida" if ok is None else ("enviada" if ok else "error")
        self.estadisticas[{"omitida": "omitidas", "enviada": "enviadas", "error": "errores"}[estado]] += 1
        try:
            conn = connect(self.db_path)
            conn.execute("INSERT INTO notificaciones (fecha, canal, asunto, estado, detalle) VALUES (?, 'telegram', ?, ?, ?)",
                         (ahora(), asunto[:200], estado, detalle[:300]))
            conn.commit()
            conn.close()
        except Exception:  # registrar nunca debe romper el envío
            log.exception("No se pudo registrar la notificación")
