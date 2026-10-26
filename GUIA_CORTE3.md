# Guía del Corte 3: subir la v1.0.0 a GitHub por fases

El docente pide ver **cómo evolucionó el MVP**, así que la v1.0.0 se sube **en el mismo repositorio**, encima de la v0.2.0, con un commit por fase. Cada paquete `c3-faseN.zip` trae **solo los archivos nuevos o modificados** de esa fase, con sus carpetas. Al subirlos, GitHub **reemplaza** los archivos con el mismo nombre.

## Antes de empezar
1. En GitHub, cambia a la rama **`desarrollo`** (botón de rama arriba a la izquierda). Si no existe, créala desde `main`.
2. Para cada fase: descomprime el zip → **Add file → Upload files** → arrastra **el contenido** de la carpeta (no la carpeta) → escribe el **mensaje del commit** → **Commit changes**.
3. Después de cada subida revisa que los archivos quedaron en su carpeta (`noc/`, `noc/routes/`, `static/js/`…).
4. Si puedes, sube las fases en momentos distintos y **lee los archivos de cada fase** antes del commit: te los van a preguntar en la sustentación.

> **Nunca subas** `.env`, la carpeta `data/` ni `respaldos/`.

---

## Fase 1 · Hallazgos del Corte 2: fechas inmutables, usuarios y API
**Paquete:** `c3-fase1.zip` (12 archivos)
`config.py`, `.gitignore`, `.env.example`, `requirements.txt`, `noc/schema.sql`, `noc/schema_triggers.sql`, `noc/db.py`, `noc/interfaces.py`, `noc/autenticacion.py`, `noc/syslog_parser.py`, `noc/routes/__init__.py`, `noc/routes/usuarios.py`

**Mensaje del commit:**
```
feat(c3-fase1): fechas inmutables, auditoria encadenada, usuarios con clave y tokens API (hallazgos H1, H4, H5, H6)
```
**Pregunta de validación:** ¿qué hace el trigger `eventos_campos_inmutables`, y por qué la cadena de hashes detecta una alteración aunque alguien borre el trigger?

## Fase 2 · Gestor SSH/consola, puertos, Telegram y defensa IA mejorada
**Paquete:** `c3-fase2.zip` (14 archivos)
`app.py`, `noc/gestor_remoto.py`, `noc/notificador.py`, `noc/hora.py`, `noc/politica.py`, `noc/ingesta.py`, `noc/simulador.py`, `noc/generador_config.py`, `noc/catalogo_acciones.py`, `noc/routes/dispositivos.py`, `noc/routes/eventos.py`, `noc/routes/incidentes.py`, `noc/routes/acciones.py`, `noc/routes/herramientas.py`

**Mensaje del commit:**
```
feat(c3-fase2): gestor SSH y consola GNS3, puertos fisicos, alertas Telegram y defensa IA (riesgo, rafagas, cambio no autorizado)
```
**Pregunta de validación:** ¿cómo decide el NOC que un cambio de configuración es «no autorizado», y por qué las credenciales SSH nunca llegan al navegador?

## Fase 3 · Interfaz v1.0.0
**Paquete:** `c3-fase3.zip` (10 archivos)
`templates/index.html`, `static/css/estilos.css`, `static/js/acceso.js`, `static/js/administracion.js`, `static/js/comun.js`, `static/js/eventos.js`, `static/js/herramientas.js`, `static/js/inventario.js`, `static/js/principal.js`, `static/js/resumen.js`

**Mensaje del commit:**
```
feat(c3-fase3): interfaz con inicio de sesion, usuarios, API, verificacion de politicas y puertos de consola e interfaces
```
**Pregunta de validación:** ¿para qué sirve la cabecera `X-NOC` que agrega `api()`, y qué ataque evita?

## Fase 4 · Pruebas y herramientas de operación
**Paquete:** `c3-fase4.zip` (12 archivos)
`tests/conftest.py`, `tests/test_api.py`, `tests/test_usuarios.py`, `tests/test_inmutabilidad.py`, `tests/test_gestor_remoto.py`, `tests/test_v1_operacion.py`, `tools/__init__.py`, `tools/respaldo.py`, `tools/restaurar.py`, `tools/prueba_carga.py`, `tools/crear_usuario.py`, `tools/equipo_virtual.py`

**Probar en el PC:**
```powershell
pip install -r requirements.txt
python -m pytest -v
```
Debe mostrar **73 passed**.

**Mensaje del commit:**
```
test(c3-fase4): pruebas de seguridad, inmutabilidad, gestor, carga, respaldo y recuperacion; herramientas de operacion
```
**Pregunta de validación:** ¿qué comprueba `tools/restaurar.py` antes de restaurar un respaldo, y por qué?

## Fase 5 · Documentación, manuales y bitácoras
**Paquete:** `c3-fase5.zip` (14 archivos)
`README.md`, `CHANGELOG.md`, `GUIA_CORTE3.md`, `docs/hallazgos_corte2.md`, `docs/manual_tecnico.md`, `docs/manual_usuario.md`, `docs/laboratorio_gns3.md`, `docs/bitacora_marcha_blanca.md`, `docs/plan_pruebas.md`, `docs/despliegue_rollback.md`, `docs/API.md`, `docs/politica_defensa_ia.md`, `docs/arquitectura.md`, `docs/requisitos.md`

Antes del commit, **completa tus datos** en `README.md` y en `docs/bitacora_marcha_blanca.md`.

**Mensaje del commit:**
```
docs(c3-fase5): manual tecnico y de usuario, laboratorio GNS3, bitacora de marcha blanca, pruebas, despliegue y rollback
```

---

## Marcha blanca (entre la fase 5 y la versión final)
1. Actualiza el proyecto en el PC con los mismos archivos.
2. Sigue `docs/laboratorio_gns3.md` y llena `docs/bitacora_marcha_blanca.md` (MB-01 a MB-20) con capturas.
3. Si encuentras errores, corrígelos y súbelos como commits `fix(marcha-blanca): …`.
4. Sube la bitácora llena: `docs(marcha-blanca): bitacora con resultados del laboratorio GNS3`.

## Release v1.0.0
1. **Pull requests → New pull request** con *base* `main` y *compare* `desarrollo` → **Create pull request** → **Merge pull request**.
2. **Releases → Draft a new release** → *Choose a tag* → escribe `v1.0.0` → **Create new tag** (desde `main`).
3. Título: `v1.0.0 – Herramienta madura (Corte 3)`. En la descripción pega la sección **v1.0.0** de `CHANGELOG.md`.
4. **Publish release**.

## Capturas sugeridas para el informe del Corte 3

| Código | Evidencia |
|--------|-----------|
| E01 | Repositorio con el historial de commits desde el Corte 2 (fases c3) |
| E02 | Pantalla de inicio de sesión y cambio de clave temporal |
| E03 | Vista Usuarios: creación del auditor con clave temporal |
| E04 | Inventario: detalle de un equipo con consola y puertos físicos |
| E05 | Puerto en rojo tras suspender un enlace en GNS3 (evento LINK-3-UPDOWN) |
| E06 | Consola real: `show ip interface brief` y un comando bloqueado |
| E07 | Aprobaciones: acción real en los 8 pasos + `show archive log config all` |
| E08 | Simulación del ataque IA: banderas y riesgo alto |
| E09 | Alerta recibida en Telegram |
| E10 | Verificación: controles globales y políticas por equipo |
| E11 | Auditoría + «Verificar integridad» |
| E12 | Vista API + petición con token (PowerShell o curl) |
| E13 | `pytest -v` con 73 passed |
| E14 | Prueba de carga, respaldo y restauración |
| E15 | Ensayo de rollback y release v1.0.0 |
