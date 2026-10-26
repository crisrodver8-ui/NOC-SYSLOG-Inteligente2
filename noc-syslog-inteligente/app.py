"""
NOC Syslog Inteligente - punto de entrada.

Ejecutar:   python app.py
Interfaz:   http://127.0.0.1:8080   (la primera vez pide crear el administrador)
Syslog UDP: puerto 5514 (configurable en .env)
"""
import logging

from flask import Flask, render_template

from config import Config
from noc import db, hora, receptor_udp
from noc.ingesta import Ingestor
from noc.notificador import NotificadorTelegram
from noc.routes import registrar_rutas


def create_app(ajustes: dict | None = None) -> Flask:
    """Crea la aplicación. 'ajustes' permite sobrescribir la configuración (pruebas)."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.sort_keys = False
    app.json.ensure_ascii = False
    if ajustes:
        app.config.update(ajustes)

    # Base de datos: crear/migrar tablas, activar inmutabilidad y cargar equipos simulados
    conn = db.connect(app.config["DB_PATH"])
    db.init_db(conn)
    db.sembrar_si_vacia(conn)
    conn.close()

    # Alertas Telegram (token solo desde .env) e ingestor compartido por la web y el receptor UDP
    notificador = NotificadorTelegram(app.config["TELEGRAM_TOKEN"], app.config["TELEGRAM_CHAT_ID"],
                                      app.config["DB_PATH"], app.config["TELEGRAM_LIMITE_MIN"])
    app.extensions["notificador"] = notificador
    app.extensions["ingestor"] = Ingestor(app.config, notificador)
    app.teardown_appcontext(db.close_db)
    registrar_rutas(app)

    @app.get("/")
    def inicio():
        return render_template("index.html", version=app.config["VERSION"])

    @app.after_request
    def cabeceras_seguridad(resp):
        # Defensa en profundidad: el navegador no ejecuta scripts externos ni incrustados
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if resp.mimetype == "application/json":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    cfg = app.config
    if cfg["SYSLOG_LISTENER"]:
        receptor_udp.iniciar(app)
    app.extensions["notificador"].iniciar()
    hora.iniciar_verificacion_periodica(cfg["NTP_SERVIDOR"], cfg["NTP_DESFASE_MAX_MS"])

    print(f"\n  NOC Syslog Inteligente v{cfg['VERSION']}")
    print(f"  Interfaz:  http://{cfg['WEB_HOST']}:{cfg['WEB_PORT']}")
    print(f"  Syslog:    UDP {cfg['SYSLOG_HOST']}:{cfg['SYSLOG_PORT']}")
    print(f"  Telegram:  {'configurado' if app.extensions['notificador'].configurado else 'sin configurar'}\n")
    try:
        from waitress import serve  # servidor WSGI de producción (funciona en Windows)
        serve(app, host=cfg["WEB_HOST"], port=cfg["WEB_PORT"], threads=8)
    except ImportError:
        app.run(host=cfg["WEB_HOST"], port=cfg["WEB_PORT"], debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
