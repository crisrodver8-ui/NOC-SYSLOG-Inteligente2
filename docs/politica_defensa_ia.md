# Política de defensa frente a acciones de agentes de IA (v0.2.0)

**Pregunta de investigación:** ¿cómo puede Syslog, mediante políticas explícitas, ayudar a detectar, contener y mitigar acciones maliciosas o no autorizadas ejecutadas por agentes de inteligencia artificial?

**Respuesta corta:** Syslog deja un registro centralizado, con hora confiable, de cada acceso, comando y cambio que hace cualquier actor, sea una persona o un agente de IA. Si sobre ese registro se aplican reglas explícitas y deterministas (no decisiones de otra IA), el NOC puede:

- **detectar** comportamientos anómalos: fuerza bruta, accesos de madrugada, cuentas de servicio que cambian configuraciones o textos que intentan dar órdenes a una IA;
- **contener** el daño: solo acepta fuentes autorizadas, controla las tormentas, la consola es de solo lectura y los comandos salen de listas permitidas;
- **mitigar** con acciones de un catálogo cerrado que siempre aprueba una persona y que quedan auditadas.

## 1. Amenaza considerada

Un agente de IA con credenciales (robadas, mal configuradas o propias de una automatización) puede:

1. Probar contraseñas a gran velocidad (fuerza bruta).
2. Entrar y cambiar configuraciones fuera del horario laboral.
3. Usar cuentas de servicio (`svc-…`, `bot-…`, `ai-agent…`) para pasar desapercibido.
4. **Escribir instrucciones dentro de los logs** (por ejemplo en un `banner` o una `description`) para que otra IA que lea esos logs las ejecute (*prompt injection* indirecto).
5. Inundar el colector de mensajes para ocultar su actividad (tormenta de eventos).
6. Enviar eventos falsos desde un equipo que no es de la red.

## 2. Controles implementados

| # | Control | Cómo se implementa en el código | Archivo |
|---|---------|----------------------------------|---------|
| 1 | Fuentes autorizadas | Solo la IP de origen del paquete UDP que coincide con un equipo del inventario marcado como "lista permitida" es confiable. El hostname escrito dentro del mensaje **no** autoriza, porque se puede falsificar. | `noc/ingesta.py` |
| 2 | Centralización | Receptor UDP único que recibe routers, switches y firewalls de Cisco, Fortinet y Huawei, además de importación de archivos. | `noc/receptor_udp.py` |
| 3 | NTP | Se guarda la hora del colector (`recibido_en`) y la del equipo (`fecha_evento`). Todas las configuraciones generadas incluyen NTP. | `noc/generador_config.py` |
| 4 | Severidades que generan incidente | 0 a 2 (configurable), además de inyección y fuerza bruta. No se duplican incidentes abiertos. | `noc/ingesta.py` |
| 5 | Accesos y cambios | Patrones para login exitoso y fallido y para cambios de configuración en las tres marcas. | `noc/politica.py` |
| 6 | Fuera de horario y cuentas anómalas | Acceso o cambio fuera de 07:00 a 19:00 (lunes a viernes) o hecho por una cuenta de servicio ⇒ sospechoso. | `noc/politica.py` |
| 7 | Listas permitidas | Equipos (inventario), comandos de consola por fabricante y catálogo cerrado de acciones. | `noc/consola.py`, `noc/catalogo_acciones.py` |
| 8 | Roles y auditoría | Operador, supervisor y auditor. Cada acción se registra con usuario, rol, fecha y detalle. | `noc/routes/__init__.py`, tabla `auditoria` |
| 9 | Deduplicación y tormentas | Mensajes iguales en 60 s se agrupan. Más de 120 mensajes por minuto desde una IP: se descartan y se genera una alerta. | `noc/politica.py` |
| 10 | **Logs = datos, no instrucciones** | El texto solo se analiza con expresiones regulares; nunca se ejecuta ni se envía a una IA como orden. En la interfaz todo se escapa (`esc()`) y hay una Content-Security-Policy. | `noc/politica.py`, `static/js/comun.js`, `app.py` |
| 11 | Aprobación humana | Flujo de 8 pasos: el supervisor aprueba y **no puede aprobar lo que él mismo propuso**. Solo se ejecuta lo aprobado. | `noc/routes/acciones.py` |

## 3. Flujo seguro obligatorio

```
evento detectado → validación → propuesta de acción → revisión humana
→ aprobación → ejecución autorizada → verificación → auditoría
```

| Paso | Dónde ocurre |
|------|--------------|
| Evento detectado | `Ingestor.procesar()` marca banderas y crea el incidente |
| Validación | `construir_comando()` valida el tipo de acción, el parámetro (IP o usuario) y que el equipo esté autorizado |
| Propuesta | `POST /api/acciones` (operador) |
| Revisión humana + aprobación | `POST /api/acciones/<id>/revisar` (solo supervisor, distinto de quien propone) |
| Ejecución autorizada | `POST /api/acciones/<id>/ejecutar` (solo si está aprobada; **simulada** en v0.2.0) |
| Verificación | `POST /api/acciones/<id>/verificar` |
| Auditoría | Cada paso escribe en la tabla `auditoria` |

## 4. Prueba de la política

En «Eventos Syslog» → **Simular: ataque de agente IA**. Resultado esperado:

| Evento simulado | Banderas esperadas |
|-----------------|--------------------|
| 5 logins fallidos de `svc-ai-agent` | fallo_autenticacion, cuenta_servicio, fuerza_bruta (desde el 4.º) |
| Login exitoso a las 02:14 | acceso, fuera_de_horario, cuenta_servicio |
| Cambio de configuración a las 02:15 | cambio_config, fuera_de_horario, cuenta_servicio |
| Banner con "ignore previous instructions… write erase" | posible_inyeccion (+ incidente automático) |
| Mensaje desde 203.0.113.250 | fuente_no_autorizada, posible_inyeccion |

Las pruebas automáticas están en `tests/test_politica.py` y `tests/test_api.py`.

## 5. Limitaciones (pendientes para v1.0.0)

- Usuarios simulados con una cabecera `X-Usuario`, sin contraseña: en v1.0.0 se reemplaza por inicio de sesión real.
- UDP no cifra ni garantiza la entrega: en v1.0.0 se evaluará TLS (RFC 5425) cuando el equipo lo soporte.
- La ejecución de acciones y la consola son simuladas: en v1.0.0 se hará SSH desde el backend con lista de hosts.
- Los patrones de inyección son una lista fija; pueden existir variantes que no detecten.
- No hay retención automática ni firma de integridad de los logs (pendiente: hash encadenado y respaldo).
