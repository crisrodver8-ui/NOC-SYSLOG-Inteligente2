# Historial de versiones

## v1.0.0 — Corte 3: herramienta madura

### Correcciones de los hallazgos del Corte 2
- Fechas inmutables: 11 triggers SQLite, auditoría encadenada SHA-256, verificación NTP del servidor y desfase de hora por evento.
- Puertos de consola por equipo (serial COM / telnet GNS3) con instrucciones de conexión.
- Puertos físicos (interfaces) con vista frontal, estado desde Syslog y lectura desde el equipo real.
- Usuarios reales con clave, roles, bloqueo por intentos y clave temporal obligatoria.
- API REST con tokens Bearer e índice automático (`/api/`).
- Claves para el auditor: clave temporal de un solo uso, solo lectura.

### Nuevo
- Gestor SSH (paramiko) y de consola telnet desde el backend, con lista de hosts, lista de comandos y huella SSH (TOFU).
- Ejecución REAL de las acciones aprobadas en equipos de laboratorio; simulada en los equipos simulados.
- Alertas por Telegram (token solo en `.env`, cola, límite por minuto y deduplicación).
- Defensa IA mejorada: `ofuscacion`, `hora_desfasada`, `rafaga_cambios`, `cambio_no_autorizado` (correlación con aprobaciones) y puntaje de riesgo 0-100.
- Vista **Verificación** de políticas Syslog por equipo y controles globales.
- Herramientas: `respaldo.py`, `restaurar.py`, `prueba_carga.py`, `crear_usuario.py`, `equipo_virtual.py`.
- Migración automática de una base de datos de v0.2.0.
- Servidor waitress.
- 73 pruebas automáticas (antes 27).

### Documentación
- Manual técnico, manual de usuario, guía del laboratorio GNS3, plan y resultados de pruebas,
  bitácora de marcha blanca, procedimiento de despliegue y rollback, API y corrección de hallazgos.

## v0.2.0 — Corte 2: MVP
- Inventario, recepción e importación Syslog, clasificación 0-7, panel, filtros, incidentes,
  configuraciones Cisco/Fortinet/Huawei, consola simulada, política IA inicial y flujo de aprobación.

## v0.1.0 — Alfa
- Modelo de datos, motor Syslog, API e interfaz inicial.
