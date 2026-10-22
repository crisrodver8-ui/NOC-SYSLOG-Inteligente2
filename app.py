"""
NOC Syslog Inteligente - punto de entrada.

Ejecutar:   python app.py
Interfaz:   http://127.0.0.1:8080
Syslog UDP: puerto 5514 (configurable en .env)
"""
import logging

from flask import Flask, render_template

from config import Config
from noc import db, receptor_udp
from noc.ingesta import Ingestor
from noc.routes import registrar_rutas


def create_app(ajustes: dict | None = None) -> Flask:
    """Crea la aplicación. 'ajustes' permite sobrescribir la configuración (pruebas)."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json.sort_keys = False  # conserva el orden original de los diccionarios en las respuestas
    if ajustes:
        app.config.update(ajustes)

    # Base de datos: crear tablas y cargar equipos simulados la primera vez
    conn = db.connect(app.config["DB_PATH"])
    db.init_db(conn)
    db.sembrar_si_vacia(conn)
    conn.close()

    # Un único Ingestor compartido por la web y el receptor UDP
    app.extensions["ingestor"] = Ingestor(app.config)
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
            "font-src https://fonts.gstatic.com; img-src 'self' data:; object-src 'none'")
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        return resp

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    aplicacion = create_app()
    if aplicacion.config["SYSLOG_LISTENER"]:
        receptor_udp.iniciar(aplicacion)
    print(f"\n  NOC Syslog Inteligente v{aplicacion.config['VERSION']}")
    print(f"  Interfaz:  http://{aplicacion.config['WEB_HOST']}:{aplicacion.config['WEB_PORT']}")
    print(f"  Syslog:    UDP {aplicacion.config['SYSLOG_HOST']}:{aplicacion.config['SYSLOG_PORT']}\n")
    aplicacion.run(host=aplicacion.config["WEB_HOST"], port=aplicacion.config["WEB_PORT"],
                   debug=False, use_reloader=False)
