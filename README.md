# NOC Syslog Inteligente · v1.0.0

Aplicación de administración de redes que recibe, clasifica y gestiona eventos **Syslog** de equipos Cisco, Fortinet y Huawei. Se conecta a los equipos del laboratorio (GNS3/EVE-NG) por **SSH o consola** desde el servidor y aplica una **política de defensa frente a acciones de agentes de IA** con aprobación humana obligatoria y auditoría inmutable.

| | |
|---|---|
| **Asignatura** | Administración y Gestión de Redes · 2026-2 |
| **Docente** | Ing. John Harold Pérez Calderón |
| **Estudiante** | _[Nombre completo]_ · _[Identificación]_ · _[Grupo]_ |
| **Versión** | v1.0.0 · Corte 3 (herramienta madura) |

> Los equipos de la semilla y sus IP (RFC 5737) son **simulados**. Los equipos reales del laboratorio se agregan en el inventario desmarcando «simulado» (ver `docs/laboratorio_gns3.md`).

## Novedades de v1.0.0
- **Correcciones del Corte 2** (`docs/hallazgos_corte2.md`): fechas inmutables, puertos de consola, puertos físicos, usuarios con clave, API con tokens y claves para el auditor.
- **Gestor SSH/consola** real con roles, lista de hosts y lista de comandos; **ejecución real** de acciones aprobadas.
- **Alertas por Telegram** sin exponer el token.
- **Defensa IA mejorada**: cambio no autorizado (correlación con aprobaciones), ráfagas, ofuscación, hora desfasada y riesgo 0-100.
- **Verificación** de políticas Syslog por equipo; **respaldo y recuperación** verificados; **despliegue y rollback**.
- 73 pruebas automáticas: funcionales, de seguridad, de carga, de respaldo y de recuperación.

Historial completo en `CHANGELOG.md`.

## Funciones
- Inventario con **acceso de administración** (consola serial/telnet y SSH) y **puertos físicos** (frente del equipo, estado desde Syslog o leído del equipo).
- Recepción UDP 5514, importación de archivos y simulador (normal, ataque de agente IA y tormenta).
- Clasificación por equipo, fabricante, fecha, facility, severidad 0-7 y **riesgo**.
- Panel, filtros, incidentes (creación, asignación, seguimiento y cierre).
- Configuraciones comentadas para Cisco, Fortinet y Huawei.
- Consola de solo lectura: simulada o **real**.
- Flujo seguro: evento → validación → propuesta → revisión humana → aprobación → ejecución → verificación → auditoría.
- Usuarios (admin, supervisor, operador, auditor), **API REST** con tokens y auditoría encadenada SHA-256.

## Instalación desde cero

Requisitos: **Python 3.10+** y Git.

```powershell
git clone https://github.com/<tu-usuario>/<tu-repositorio>.git
cd <tu-repositorio>
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/macOS: cp .env.example .env
```

## Ejecución

```powershell
python app.py
```

- Interfaz: <http://127.0.0.1:8080>. La primera vez pide **crear el administrador**.
- Receptor Syslog: UDP `0.0.0.0:5514`.
- Detener: `Ctrl + C`.

### Primeros pasos
1. Crea el administrador y, en **Usuarios**, crea al operador, al supervisor y al **auditor**. Cada uno recibe una clave temporal.
2. **Eventos Syslog** → simula tráfico normal y un ataque de agente IA.
3. **Inventario** → abre un equipo para ver su consola y sus puertos.
4. Laboratorio real: sigue `docs/laboratorio_gns3.md`. Sin GNS3: `python tools/equipo_virtual.py --syslog 127.0.0.1:5514`.

## Pruebas

```powershell
python -m pytest -v
```

Detalle y resultados en `docs/plan_pruebas.md`.

## Herramientas

| Comando | Para qué |
|---------|----------|
| `python tools/respaldo.py --conservar 14` | Respaldo en caliente verificado (SHA-256) |
| `python tools/restaurar.py <respaldo.db>` | Recuperación (con la app detenida) |
| `python tools/prueba_carga.py --token noc_xxx` | Prueba de carga UDP |
| `python tools/crear_usuario.py --usuario x --rol admin` | Crear usuario desde la terminal |
| `python tools/equipo_virtual.py` | Router Cisco virtual (SSH 2222 / telnet 5099) |
| `python tools/enviar_syslog.py` | Enviar Syslog de prueba |

## Documentación

| Documento | Contenido |
|-----------|-----------|
| `docs/hallazgos_corte2.md` | Corrección de las observaciones del Corte 2 |
| `docs/manual_tecnico.md` | Instalación, configuración, arquitectura, seguridad y operación |
| `docs/manual_usuario.md` | Uso de cada vista por rol |
| `docs/laboratorio_gns3.md` | Topología, configuración de equipos e integración |
| `docs/bitacora_marcha_blanca.md` | Plan y registro de la marcha blanca |
| `docs/plan_pruebas.md` | Pruebas funcionales, de seguridad, de carga, de respaldo y de recuperación |
| `docs/despliegue_rollback.md` | Procedimiento de despliegue y rollback |
| `docs/politica_defensa_ia.md` | Política de defensa frente a agentes de IA |
| `docs/API.md` | API REST |
| `docs/arquitectura.md` / `docs/requisitos.md` | Diseño, modelo de datos, requisitos e historias |

## Seguridad
- Secretos solo en `.env` (token de Telegram, credenciales SSH, clave de sesión). `.env`, `data/` y `respaldos/` están en `.gitignore`.
- Claves con hash, bloqueo por intentos, sesión con vencimiento, CSRF y tokens revocables.
- Fechas inmutables (triggers) y auditoría encadenada SHA-256.
- Logs tratados como datos no confiables: escape, CSP y nunca se usan como instrucciones.
- Cambios en los equipos solo por acciones del catálogo aprobadas por un supervisor distinto de quien propone.

## Limitaciones
- Syslog por UDP sin TLS; la consola telnet de GNS3 sin cifrado (solo hacia el propio PC).
- Sin doble factor de autenticación.
- Pensado para un laboratorio: para producción se recomienda HTTPS delante de waitress.

## Versiones

| Versión | Contenido |
|---------|-----------|
| v0.1.0 | Alfa |
| v0.2.0 | MVP del Corte 2 |
| v1.0.0 | Herramienta madura del Corte 3 |
