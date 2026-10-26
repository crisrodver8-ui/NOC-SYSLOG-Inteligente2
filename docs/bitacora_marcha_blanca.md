# Bitácora de marcha blanca · v1.0.0

**Marcha blanca:** operación controlada del NOC con equipos reales del laboratorio (GNS3), antes de declarar la versión final. Se verifica que todo funcione de punta a punta y se registra cada actividad con su evidencia.

## 1. Datos de la marcha blanca

| Campo | Valor |
|-------|-------|
| Responsable | _[Nombre completo]_ |
| Ambiente | GNS3 _[versión]_ con GNS3 VM / EVE-NG; NOC en Windows _[versión]_; Python _[versión]_ |
| Topología | `docs/laboratorio_gns3.md` §1 |
| Equipos autorizados | R1-BORDE (192.168.56.11), SW1-ACCESO (192.168.56.12), _[otros]_ |
| Período | Del _[fecha]_ al _[fecha]_ (mínimo 2 sesiones de trabajo) |
| Versión | v1.0.0 (commit _[hash]_) |
| Criterio de salida | Todas las actividades MB-01 a MB-18 «Cumple»; los hallazgos críticos, corregidos |

## 2. Checklist diario de operación

| Control | Día 1 | Día 2 | Día 3 |
|---------|-------|-------|-------|
| `python app.py` arranca sin errores (waitress, receptor activo) | ☐ | ☐ | ☐ |
| Verificación: receptor ✔, fechas inmutables ✔, integridad ✔ | ☐ | ☐ | ☐ |
| Hora NTP del servidor sincronizada | ☐ | ☐ | ☐ |
| Cada equipo del laboratorio envía Syslog (24 h) | ☐ | ☐ | ☐ |
| Respaldo del día creado (`tools/respaldo.py`) | ☐ | ☐ | ☐ |
| Incidentes abiertos revisados y asignados | ☐ | ☐ | ☐ |

## 3. Actividades

**Estado:** Cumple / No cumple / Cumple con observación. **Evidencia:** número de captura o archivo.

| ID | Fecha y hora | Actividad | Resultado esperado | Resultado obtenido | Estado | Evidencia | Responsable |
|----|--------------|-----------|--------------------|--------------------|--------|-----------|-------------|
| MB-01 | | Instalación limpia desde GitHub (`git clone`, venv, `pip`, `.env`) y `pytest` | 73 passed | | | | |
| MB-02 | | Configuración inicial: admin, operador, supervisor y auditor con clave temporal | Cada uno cambia su clave en el primer ingreso | | | | |
| MB-03 | | Registrar R1-BORDE y SW1-ACCESO (IP, consola GNS3, SSH, puertos) | Detalle con acceso de administración | | | | |
| MB-04 | | Aplicar la configuración Syslog generada a R1 y SW1 | `show logging` apunta a 192.168.56.1:5514 | | | | |
| MB-05 | | Recepción real: suspender el enlace R1 Gi0/1 – SW1 Gi0/1 en GNS3 | Evento `LINK-3-UPDOWN`; puerto en rojo en el frente del equipo | | | | |
| MB-06 | | Prueba de inyección: `description ignore previous instructions <script>` en una interfaz desde la consola de GNS3 | Evento con `posible_inyeccion`; se ve como texto; incidente automático | | | | |
| MB-07 | | Cambio fuera del flujo (desde la consola de GNS3, sin aprobación) | `cambio_no_autorizado` + incidente | | | | |
| MB-08 | | Fuerza bruta: 5 intentos SSH fallidos a R1 desde Windows (`ssh malo@192.168.56.11`) | `fuerza_bruta` + incidente | | | | |
| MB-09 | | Fuente no autorizada: marcar SW1 como NO autorizado y generar un evento | `fuente_no_autorizada` | | | | |
| MB-10 | | Hora desfasada: `clock set` con 1 h de diferencia en SW1 | `hora_desfasada`; la verificación de SW1 en rojo | | | | |
| MB-11 | | Consola real: `show ip interface brief` en R1 (SSH) y en SW1 (consola telnet) | Salida real del equipo; auditado | | | | |
| MB-12 | | Consola: `configure terminal` y `show version ; reload` | Bloqueados y auditados | | | | |
| MB-13 | | Leer puertos de R1 y SW1 | Puertos reales cargados | | | | |
| MB-14 | | Flujo seguro real: operador propone «Bloquear IP 203.0.113.66» en R1 → otro supervisor aprueba → ejecutar → verificar con `show archive log config all` | Línea `deny ip host 203.0.113.66` en R1; 8 pasos en verde | | | | |
| MB-15 | | El mismo supervisor intenta aprobar su propia acción | Rechazado (cuatro ojos) | | | | |
| MB-16 | | Telegram: Enviar prueba + un evento severidad 2 | Llegan las 2 alertas; token no visible en la interfaz | | | | |
| MB-17 | | Carga: `tools/prueba_carga.py --mensajes 2000 --tasa 200` | Recibidos ≥ 99 %; la interfaz responde | | | | |
| MB-18 | | Respaldo → borrar `data/noc.db` (con la app detenida) → restaurar | Datos recuperados; integridad ✔ | | | | |
| MB-19 | | Ensayo de despliegue y rollback (`docs/despliegue_rollback.md`) | Vuelve a v0.2.0 y regresa a v1.0.0 | | | | |
| MB-20 | | Auditor: verificar integridad y revisar la auditoría de la jornada | Cadena íntegra; acciones de todos los usuarios visibles | | | | |

## 4. Incidencias encontradas durante la marcha blanca

| # | Fecha | Descripción | Severidad | Causa | Corrección (commit) | Estado |
|---|-------|-------------|-----------|-------|---------------------|--------|
| 1 | | | | | | |

## 5. Ejecución de referencia (antes de GNS3)

Se ensayó el procedimiento con el **equipo virtual** (`tools/equipo_virtual.py`, router Cisco emulado con SSH en 2222 y consola telnet en 5099) en el entorno de desarrollo, el 26/10/2026:

| Actividad | Resultado |
|-----------|-----------|
| Configuración inicial y creación de operador1, supervisor1 y auditor1 con clave temporal | Cumple: cambio de clave obligatorio en el primer ingreso |
| Equipo real R-GNS3 (SSH 127.0.0.1:2222, consola telnet 127.0.0.1:5099) | Cumple: «Probar conexión» OK |
| Leer puertos del equipo | Cumple: 4 puertos (Gi0/0 arriba, Gi0/1 apagado, Gi0/2 abajo, Loopback0) |
| Consola real `show ip interface brief` / `configure terminal` | Cumple: salida real / bloqueado |
| Acción aprobada «Bloquear IP» ejecutada por SSH | Cumple: el equipo registró `deny ip host 203.0.113.66` |
| Simulación de ataque IA | Cumple: 8 tipos de bandera, incidentes automáticos |
| Carga UDP 2000 mensajes a 400 msg/s | Cumple: 100 % recibidos |
| Respaldo y restauración | Cumple: 204 eventos y 34 registros de auditoría recuperados; respaldo alterado rechazado |

> Esta ejecución de referencia **no reemplaza** la marcha blanca en GNS3: es el ensayo previo. Las filas MB-01 a MB-20 se llenan con los equipos del laboratorio.

## 6. Conclusión de la marcha blanca

_[Resumen: actividades cumplidas, incidencias y correcciones, y si la versión v1.0.0 queda aprobada para la entrega.]_

Firma del responsable: ______________________ Fecha: __________
