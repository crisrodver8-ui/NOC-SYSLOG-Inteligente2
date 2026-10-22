# Problema, objetivos, requisitos e historias de usuario (v0.2.0)

> Plantilla con contenido base. **Redáctala con tus propias palabras** antes de pasarla al informe.

## Problema

En una red con equipos de varios fabricantes (Cisco, Fortinet, Huawei), cada equipo guarda sus propios registros. Sin un punto central, el administrador no ve a tiempo las fallas ni los accesos indebidos. Además, hoy los agentes de IA y las automatizaciones tienen credenciales y pueden hacer cambios rápidos y difíciles de rastrear. Se necesita una herramienta que reúna los eventos, los clasifique por severidad, detecte comportamientos sospechosos y obligue a que una persona apruebe cualquier acción sobre los equipos.

## Objetivo general

Desarrollar un MVP de NOC que reciba, clasifique y gestione eventos Syslog de equipos multivendor, con políticas explícitas de defensa frente a acciones de agentes de IA y con aprobación humana obligatoria.

## Objetivos específicos

1. Mantener un inventario editable de equipos que sirva como lista permitida de fuentes.
2. Recibir mensajes Syslog por UDP y por importación de archivos, y clasificarlos por equipo, fabricante, fecha, facility y severidad.
3. Mostrar un panel con el estado de los equipos, los eventos recientes y críticos y los incidentes.
4. Gestionar incidentes de punta a punta: creación, asignación, seguimiento y cierre.
5. Generar configuraciones Syslog comentadas para Cisco, Fortinet y Huawei.
6. Aplicar una política de defensa frente a agentes de IA con flujo de aprobación humana y auditoría.

## Alcance y limitaciones

- **Incluye:** todas las funciones del MVP con datos y equipos **simulados** (IP de documentación del RFC 5737).
- **No incluye (v1.0.0):** SSH real, alertas por Telegram, inicio de sesión con contraseña ni TLS para Syslog.

## Requisitos funcionales

| ID | Requisito | Prioridad |
|----|-----------|-----------|
| RF01 | Registrar, editar y eliminar equipos con nombre, IP, marca, modelo, versión, ubicación, estado y fecha | Alta |
| RF02 | Recibir Syslog por UDP e importar archivos .log/.txt | Alta |
| RF03 | Clasificar por equipo, fabricante, fecha, facility y severidad 0-7 | Alta |
| RF04 | Panel con KPIs, actividad, severidades, salud de equipos, alertas e incidentes | Alta |
| RF05 | Filtrar eventos por fecha, marca, equipo, severidad, texto y sospechosos | Alta |
| RF06 | Crear, asignar, dar seguimiento y cerrar incidentes | Alta |
| RF07 | Generar configuraciones comentadas para Cisco, Fortinet y Huawei | Alta |
| RF08 | Consola simulada con comandos permitidos y bloqueados | Alta |
| RF09 | Proponer, aprobar, ejecutar (simulado) y verificar acciones | Alta |
| RF10 | Registrar en la auditoría todas las acciones relevantes | Alta |

## Requisitos no funcionales

| ID | Requisito |
|----|-----------|
| RNF01 | Ningún secreto en el código (uso de `.env`) |
| RNF02 | Todo dato del log se muestra escapado (sin ejecución de HTML o JS) |
| RNF03 | Consultas SQL parametrizadas (sin inyección SQL) |
| RNF04 | El receptor no se cae ante mensajes malformados |
| RNF05 | La interfaz funciona en escritorio y en celular |
| RNF06 | Instalación desde cero en menos de 10 minutos |

## Historias de usuario

**HU01 – Inventario.** Como *operador* quiero registrar los equipos de la red para saber cuáles están autorizados a enviar eventos.
*Criterios:* (1) no permite IP inválida ni duplicada; (2) guarda la fecha de actualización; (3) solo el supervisor elimina.

**HU02 – Recepción.** Como *operador* quiero que los eventos lleguen solos por UDP o poder importarlos desde un archivo.
*Criterios:* (1) un mensaje enviado al puerto 5514 aparece en «Eventos»; (2) al importar se muestra cuántos eventos son nuevos y cuántos duplicados.

**HU03 – Clasificación y filtros.** Como *operador* quiero filtrar por severidad, marca, equipo y fecha para encontrar rápido lo importante.
*Criterios:* (1) al filtrar por severidad 4 solo aparecen severidad 4; (2) se puede combinar filtros.

**HU04 – Panel.** Como *supervisor* quiero ver en una pantalla el estado de la red.
*Criterios:* (1) KPIs de equipos, eventos, críticos, sospechosos, incidentes y aprobaciones; (2) se actualiza cada 15 s.

**HU05 – Incidentes.** Como *operador* quiero crear, asignar y cerrar incidentes con su historial.
*Criterios:* (1) no se cierra sin una solución; (2) cada cambio queda como nota; (3) los eventos graves crean el incidente solos.

**HU06 – Configuraciones.** Como *administrador* quiero generar la configuración Syslog de cada marca para no escribirla a mano.
*Criterios:* (1) incluye comentarios, NTP y comandos de verificación; (2) rechaza IP inválidas.

**HU07 – Consola.** Como *operador* quiero consultar los equipos sin riesgo de cambiarlos.
*Criterios:* (1) `show version` responde; (2) `configure terminal` o `reload` se bloquean; (3) el intento queda auditado.

**HU08 – Defensa IA.** Como *supervisor* quiero que los eventos sospechosos de un agente de IA se marquen y que ninguna acción se ejecute sin mi aprobación.
*Criterios:* (1) un log con "ignore previous instructions" se marca como posible inyección; (2) quien propone no puede aprobar; (3) no se ejecuta nada sin aprobación.
