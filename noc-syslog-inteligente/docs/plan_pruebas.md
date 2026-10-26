# Plan y resultados de pruebas · v1.0.0

Hay dos tipos de prueba:
- **Automáticas** (`python -m pytest -v`): se repiten en cualquier PC.
- **Manuales y de laboratorio**: se ejecutan durante la marcha blanca y se registran en `docs/bitacora_marcha_blanca.md`.

## Resumen de la ejecución de referencia

| Tipo | Cantidad | Resultado | Archivo |
|------|----------|-----------|---------|
| Funcionales (API de extremo a extremo) | 13 | ✔ | `tests/test_api.py` |
| Parser Syslog multivendor | 7 | ✔ | `tests/test_parser.py` |
| Política IA (reglas) | 5 | ✔ | `tests/test_politica.py` |
| Seguridad: consola y catálogo | 2 | ✔ | `tests/test_seguridad.py` |
| Seguridad: usuarios, claves, roles, CSRF y API | 13 | ✔ | `tests/test_usuarios.py` |
| Inmutabilidad, integridad y migración | 12 | ✔ | `tests/test_inmutabilidad.py` |
| Gestor SSH/consola contra equipo virtual | 7 | ✔ | `tests/test_gestor_remoto.py` |
| Defensa IA v1, puertos, Telegram, verificación, carga, respaldo, recuperación y NTP | 14 | ✔ | `tests/test_v1_operacion.py` |
| **Total** | **73** | **73 passed** | |

> Ejecución de referencia del 26/10/2026 en el entorno de desarrollo (Python 3.13, Linux). **Repítela en el PC del laboratorio** y adjunta la captura de `pytest -v` como evidencia (E12).

## 1. Pruebas funcionales

| ID | Objetivo | Procedimiento | Resultado esperado | Prueba automática |
|----|----------|---------------|--------------------|-------------------|
| PF-01 | CRUD de inventario | Crear, editar y eliminar un equipo | IP inválida o duplicada rechazada; solo el supervisor elimina | `test_inventario_crud` |
| PF-02 | Importación | Importar `samples/syslog_simulado.log` | 11 líneas, equipos asociados por nombre | `test_importar_archivo` |
| PF-03 | Clasificación y filtros | Filtrar por severidad 4 y por marca | Solo aparecen los que cumplen | `test_filtro_por_severidad` |
| PF-04 | Ciclo del incidente | Crear → asignar → en progreso → resuelto (con solución) → cerrado | Transiciones inválidas rechazadas; notas automáticas | `test_ciclo_de_incidente` |
| PF-05 | Flujo seguro | Proponer → aprobar (otro supervisor) → ejecutar → verificar | Sin aprobación no se ejecuta; queda en la auditoría | `test_flujo_seguro_de_acciones` |
| PF-06 | Configuraciones | Generar Cisco, Fortinet y Huawei | Contienen el servidor; rechaza inyección en la IP | `test_generador_configuraciones` |
| PF-07 | Puertos | CRUD de puertos y estado desde Syslog | `LINK-3-UPDOWN down` pone el puerto en «abajo» | `test_syslog_actualiza_estado_del_puerto`, `test_crud_de_puertos_y_consola` |
| PF-08 | Gestor real | SSH y consola telnet a un equipo | `show clock` responde; lee 4 puertos | `test_ssh_consulta_real`, `test_consola_telnet_gns3_y_sincronizar_puertos` |
| PF-09 | Ejecución real | Acción aprobada «Bloquear IP» | El equipo registra `deny ip host 203.0.113.66` | `test_accion_aprobada_se_ejecuta_en_el_equipo` |
| PF-10 | Verificación de políticas | `GET /api/verificacion` | Fechas inmutables e integridad ✔ | `test_verificacion_de_politicas` |
| PF-11 | Telegram | Alertas con límite y deduplicación | 2 enviadas, el resto omitidas; log escapado | `test_telegram_alerta_sin_exponer_token` |

## 2. Pruebas de seguridad

| ID | Riesgo | Prueba | Resultado esperado | Automática |
|----|--------|--------|--------------------|------------|
| PS-01 | Acceso sin autenticación | Pedir datos sin sesión o con token falso, o con la cabecera `X-Usuario` de v0.2.0 | 401 | `test_requiere_usuario` |
| PS-02 | Enumeración de usuarios | Login con usuario inexistente vs. clave mala | Mismo mensaje | `test_clave_incorrecta_mensaje_generico` |
| PS-03 | Fuerza bruta al login | 5 claves malas | Cuenta bloqueada | `test_bloqueo_por_intentos` |
| PS-04 | Claves débiles | Claves cortas, solo letras, con el usuario | Rechazadas | `test_politica_de_claves` |
| PS-05 | Clave temporal del auditor | Primer ingreso | Solo puede cambiar la clave; después, solo lectura | `test_admin_crea_auditor_con_clave_temporal` |
| PS-06 | Escalada de privilegios | Operador, supervisor o auditor administrando usuarios | 403 | `test_solo_admin_gestiona_usuarios` |
| PS-07 | CSRF | POST con sesión sin `X-NOC` | 403 | `test_proteccion_csrf` |
| PS-08 | Token robado | Revocar el token | 401 inmediato | `test_token_api_crear_usar_revocar` |
| PS-09 | Cuenta desactivada | Desactivar un usuario | Pierde sesión y tokens | `test_usuario_desactivado_pierde_acceso` |
| PS-10 | Alterar fechas | UPDATE de `recibido_en`, `fecha_evento`, `creado_en` | La BD lo rechaza | `test_evento_no_se_puede_modificar`, `test_fecha_creacion_incidente_inmutable` |
| PS-11 | Borrar huellas | DELETE/UPDATE en la auditoría | Rechazado; si se fuerza, la cadena lo detecta | `test_auditoria_no_se_modifica_ni_borra`, `test_cadena_detecta_alteracion` |
| PS-12 | Fechas enviadas por el usuario | `creado_en` en el JSON | Se ignora | `test_api_ignora_fechas_enviadas_por_el_usuario` |
| PS-13 | Comandos peligrosos | `configure terminal`, `write erase`, `show version ; reload` | Bloqueados antes de conectar | `test_consola_bloquea_y_audita`, `test_consola_permite_y_bloquea` |
| PS-14 | Hosts no permitidos | Consola a un host fuera de la lista | Rechazado | `test_lista_de_hosts_de_consola`, `test_equipo_no_autorizado_no_se_conecta` |
| PS-15 | Fuga de credenciales | Detalle del equipo | No incluye la clave SSH | `test_credenciales_nunca_se_devuelven` |
| PS-16 | Inyección en parámetros | `1.1.1.1\nreload` como IP | 400 | `test_accion_con_parametro_malicioso`, `test_catalogo_valida_parametros` |
| PS-17 | Prompt injection / ofuscación | Simular ataque IA | Todas las banderas presentes | `test_ataque_ia_completo_genera_todas_las_alertas` |
| PS-18 | XSS por logs | Log con `<script>` | Se muestra como texto (escape + CSP) | Manual: ver MB-06 |

## 3. Prueba de carga básica

| ID | Escenario | Resultado de referencia | Criterio |
|----|-----------|-------------------------|----------|
| PC-01 | Ingesta directa de 5000 mensajes (90 % duplicados) | 1,04 s → **≈ 4800 msg/s** | ≥ 100 msg/s |
| PC-02 | Ingesta directa de 3000 mensajes únicos | 0,89 s → **≈ 3350 msg/s** | ≥ 100 msg/s |
| PC-03 | `test_carga_basica_2000_mensajes` (20 fuentes) | < 20 s | Automática ✔ |
| PC-04 | UDP real: `tools/prueba_carga.py --mensajes 2000 --tasa 400` | 2000/2000 recibidos (0 % pérdida); 120 almacenados y 1880 descartados por el control de tormentas (una sola fuente) | Recibidos ≥ 99 % y la interfaz responde |

En el laboratorio, ejecuta PC-04 con el NOC encendido y registra el resultado. Con una sola fuente, el control de tormentas descarta lo que supera 120 mensajes por minuto: **es el comportamiento esperado**.

## 4. Respaldo y recuperación

| ID | Prueba | Procedimiento | Resultado de referencia |
|----|--------|---------------|-------------------------|
| PR-01 | Respaldo en caliente | `python tools/respaldo.py` con la app encendida | 236 KB; integridad OK; auditoría OK; SHA-256 guardado |
| PR-02 | Recuperación ante pérdida | Restaurar en una ruta vacía | Mismos 204 eventos y 34 registros de auditoría; cadena íntegra |
| PR-03 | Respaldo alterado | Modificar el .db y restaurar | Rechazado: «la huella SHA-256 no coincide» |
| PR-04 | Rollback de software | v0.2.0 sobre una BD migrada | Funciona (panel 200, simulación OK) |
| PR-05 | Migración v0.2.0 → v1.0.0 | Abrir una BD de v0.2.0 | Columnas agregadas, auditoría encadenada, triggers activos |

Automáticas: `test_respaldo_y_recuperacion`, `test_migracion_desde_v020`.
