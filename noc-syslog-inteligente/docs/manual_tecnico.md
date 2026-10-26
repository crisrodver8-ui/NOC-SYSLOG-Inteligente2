# Manual técnico · NOC Syslog Inteligente v1.0.0

## 1. Requisitos

| Componente | Versión |
|------------|---------|
| Sistema operativo | Windows 10/11 o Linux |
| Python | 3.10 o superior (probado en 3.13 y 3.15) |
| Dependencias | Flask 3, python-dotenv, waitress, paramiko, pytest (`requirements.txt`) |
| Navegador | Chrome, Edge o Firefox actualizados |
| Laboratorio | GNS3 2.2+ (con GNS3 VM para IOSv) o EVE-NG |
| Puertos | TCP 8080 (web), UDP 5514 (Syslog) |

## 2. Instalación desde cero

```powershell
git clone https://github.com/<usuario>/<repositorio>.git
cd <repositorio>
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux: cp .env.example .env
python -m pytest -q               # debe terminar con «passed»
python app.py
```

La primera vez, la interfaz (`http://127.0.0.1:8080`) pide crear el **administrador**. Si se pierde el acceso: `python tools/crear_usuario.py --usuario admin2 --rol admin`.

## 3. Configuración (`.env`)

| Variable | Defecto | Uso |
|----------|---------|-----|
| `WEB_HOST` / `WEB_PORT` | 127.0.0.1 / 8080 | Dirección de la interfaz. Usa `0.0.0.0` para abrirla a la red del laboratorio. |
| `FLASK_SECRET_KEY` | aleatoria en `data/secret_key` | Firma de las cookies de sesión |
| `SESION_HORAS` | 8 | Vencimiento de la sesión |
| `SYSLOG_HOST` / `SYSLOG_PORT` | 0.0.0.0 / 5514 | Receptor UDP |
| `NOC_DB_PATH` / `RESPALDOS_DIR` | data/noc.db / respaldos | Base de datos y respaldos |
| `DEDUP_VENTANA_S`, `LIMITE_MENSAJES_MIN`, `HORARIO_INICIO`, `HORARIO_FIN`, `SEVERIDAD_AUTO_INCIDENTE`, `DESFASE_MAX_S`, `RAFAGA_CAMBIOS` | 60, 120, 7, 19, 2, 300, 5 | Parámetros de la política |
| `NTP_SERVIDOR` / `NTP_DESFASE_MAX_MS` | pool.ntp.org / 2000 | Verificación de la hora del servidor |
| `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID` | vacío | Alertas Telegram |
| `TELEGRAM_SEVERIDAD_MAX` / `TELEGRAM_LIMITE_MIN` | 2 / 20 | Qué se alerta y cuántas por minuto |
| `SSH_USUARIO` / `SSH_CLAVE` | vacío | Credenciales de los equipos (`SSH_CLAVE_<NOMBRE>` para uno en particular) |
| `CONSOLA_HOSTS_PERMITIDOS` | 127.0.0.1,localhost | Hosts permitidos para la consola telnet |

### Alertas por Telegram
1. En Telegram, habla con **@BotFather** → `/newbot` → copia el token en `TELEGRAM_TOKEN`.
2. Escribe cualquier mensaje a tu bot y abre `https://api.telegram.org/bot<TOKEN>/getUpdates`: el número `chat.id` va en `TELEGRAM_CHAT_ID`. Para un grupo, agrega el bot al grupo; el id empieza con `-`.
3. Reinicia el NOC → **Verificación** → **Enviar prueba** (rol admin).

El token nunca se muestra completo, no se registra en logs ni en la BD, y está fuera de GitHub por `.gitignore`.

## 4. Arquitectura

Ver `docs/arquitectura.md`. En resumen:

```
Equipos ──UDP 5514──► receptor_udp ─┐
Archivo / simulador ──► API ────────┼──► ingesta ──► parser ──► política ──► SQLite
                                     │                   │
Navegador ◄──sesión/CSRF──► API REST ◄── tokens          ├──► incidentes / Telegram
                                     └──► gestor_remoto ──SSH / telnet consola──► equipos
```

| Módulo | Responsabilidad |
|--------|-----------------|
| `app.py` | Crea la app, cabeceras de seguridad, arranca receptor, Telegram, NTP y waitress |
| `config.py` | Configuración desde `.env` |
| `noc/db.py`, `schema.sql`, `schema_triggers.sql` | Modelo, migración, inmutabilidad y auditoría encadenada |
| `noc/autenticacion.py` | Claves, bloqueo, clave temporal y tokens |
| `noc/syslog_parser.py` | RFC 5424/3164, Cisco, Fortinet y Huawei |
| `noc/politica.py` | Reglas, riesgo, deduplicación y tormentas |
| `noc/ingesta.py` | Canal único de procesamiento, puertos, incidentes y alertas |
| `noc/interfaces.py` | Normalización de nombres y lectura de puertos |
| `noc/gestor_remoto.py` | SSH (paramiko) y consola telnet con listas permitidas |
| `noc/notificador.py` | Telegram con cola, límite y deduplicación |
| `noc/hora.py` | Cliente SNTP |
| `noc/routes/*` | API REST por módulo |
| `static/js/*` | Una vista por archivo |
| `tools/*` | Respaldo, restauración, carga, usuario, equipo virtual y envío UDP |

## 5. Seguridad

| Aspecto | Implementación |
|---------|----------------|
| Autenticación | Clave con hash (werkzeug scrypt), 10+ caracteres con letras y números, bloqueo de 15 min tras 5 fallos, mensaje genérico |
| Sesión | Cookie firmada `HttpOnly` + `SameSite=Strict`, vence en 8 h, se invalida al cambiar la clave |
| CSRF | Las escrituras desde el navegador exigen la cabecera `X-NOC: 1` |
| Autorización | Roles con jerarquía (admin ⊃ supervisor ⊃ operador; auditor solo lectura), validados en cada ruta |
| API | Tokens Bearer (solo el hash en la BD), vencimiento y revocación |
| Datos no confiables | Logs escapados en la interfaz, CSP sin scripts en línea, SQL parametrizado |
| Inmutabilidad | 11 triggers + auditoría encadenada SHA-256 + verificación NTP |
| Equipos | Lista de hosts, lista de comandos, catálogo de acciones, aprobación de un supervisor distinto, huella SSH (TOFU), credenciales en `.env` |
| Secretos | `.env`, `data/` y `respaldos/` excluidos de Git |

## 6. Operación

| Tarea | Comando o vista |
|-------|-----------------|
| Arrancar / detener | `python app.py` / `Ctrl+C` |
| Respaldo (diario) | `python tools/respaldo.py --conservar 14` |
| Restaurar | Detener la app → `python tools/restaurar.py respaldos/noc-AAAAMMDD-HHMMSS.db` |
| Verificar integridad | Vista **Verificación** o `GET /api/integridad` |
| Prueba de carga | `python tools/prueba_carga.py --token noc_xxx --mensajes 2000 --tasa 200` |
| Equipo de prueba | `python tools/equipo_virtual.py --syslog 127.0.0.1:5514` |
| Pruebas automáticas | `python -m pytest -v` |

**Respaldo programado en Windows:** Programador de tareas → Crear tarea básica → diaria → programa `C:\ruta\.venv\Scripts\python.exe`, argumentos `tools\respaldo.py --conservar 14`, iniciar en la carpeta del proyecto.

## 7. Base de datos

Tablas: `usuarios`, `api_tokens`, `dispositivos`, `interfaces`, `eventos`, `incidentes`, `incidente_notas`, `acciones`, `auditoria`, `notificaciones` y `esquema_version`. El diagrama entidad-relación está en `docs/arquitectura.md`.

Al arrancar, `db.init_db()` crea lo que falte, **migra** una BD de v0.2.0 (agrega columnas y encadena la auditoría antigua) y activa los triggers.

## 8. Solución de problemas

| Problema | Solución |
|----------|----------|
| `Receptor UDP apagado` | El puerto 5514 está ocupado: cambia `SYSLOG_PORT` |
| La sesión se cierra sola | Venció (8 h) o se cambió la clave; vuelve a ingresar |
| «Falta la cabecera de protección CSRF» | Se usó la sesión desde fuera de la interfaz: usa un token Bearer |
| Hora NTP «sin datos» | Sin salida a internet al puerto UDP 123: configura `NTP_SERVIDOR` con un servidor del laboratorio |
| Problemas con GNS3 | Ver `docs/laboratorio_gns3.md` §5 |
