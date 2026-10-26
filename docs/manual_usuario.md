# Manual de usuario · NOC Syslog Inteligente v1.0.0

## 1. Ingreso

1. Abre `http://127.0.0.1:8080` (o la dirección que te indique el administrador).
2. Escribe tu **usuario** y **clave**. Si es tu primer ingreso, se te pedirá cambiar la **clave temporal** por una personal: mínimo 10 caracteres, con letras y números, sin incluir tu usuario.
3. Tras 5 intentos fallidos la cuenta se bloquea 15 minutos.
4. Arriba a la derecha: **Clave** (cambiar tu clave) y **Salir**.

**Primer uso del sistema:** si no existe ningún usuario, la pantalla pide crear el **administrador**.

## 2. Roles

| Rol | Puede |
|-----|-------|
| **Operador** | Ver todo, simular o importar eventos, gestionar inventario y puertos, crear y trabajar incidentes, usar la consola, **proponer**, ejecutar y verificar acciones aprobadas |
| **Supervisor** | Lo del operador + **aprobar o rechazar** acciones (no las suyas), eliminar equipos, ver la auditoría |
| **Auditor** | **Solo lectura** + auditoría + verificación de integridad |
| **Admin** | Todo + crear usuarios, cambiar roles, restablecer claves y probar Telegram |

## 3. Vistas

### Panel general
KPIs de las últimas 24 horas (equipos, eventos, severidad 0-3, sospechosos y riesgo alto, incidentes, acciones por aprobar), actividad por hora, distribución por severidad, salud de los equipos (verde OK, ámbar sospechoso, rojo crítico, gris inactivo; muestra puertos abajo), alertas recientes e incidentes activos. Se actualiza cada 15 segundos.

### Eventos Syslog
- **Filtros:** fecha, marca, equipo, severidad, riesgo, texto y «solo sospechosos».
- **Columnas:** severidad, equipo, mensaje, repeticiones (deduplicación), **riesgo 0-100** y banderas de la política.
- **Clic en una fila:** detalle con la hora del colector (confiable) y la del equipo con su desfase, el mensaje original, y los botones **Crear incidente** y **Proponer acción**.
- **Importar archivo .log:** un mensaje Syslog por línea.
- **Simular:** tráfico normal, ataque de agente IA o tormenta de eventos.

### Incidentes
Lista por estado. Clic para ver el detalle: asignar, cambiar el estado (abierto → en progreso → resuelto → cerrado; para resolver o cerrar se exige la solución), agregar notas de seguimiento y proponer acciones. Las notas y las fechas no se pueden modificar.

### Aprobaciones (flujo seguro)
Cada acción muestra los 8 pasos: evento → validación → propuesta → revisión humana → aprobación → ejecución → verificación → auditoría.
1. **Operador:** «Proponer acción» → equipo, acción del catálogo, parámetro y justificación.
2. **Supervisor (otra persona):** Aprobar o Rechazar con un comentario.
3. **Operador:** «Ejecutar». En un equipo **real** los comandos se envían por SSH o consola; en uno simulado se registra una ejecución simulada.
4. **Operador:** «Verificar»: describe cómo comprobaste el resultado (por ejemplo con `show archive log config all` en la Consola).

### Inventario
Tabla de equipos con consola, gestión, puertos arriba y lista permitida. **Clic en un equipo** para ver:
- **Acceso de administración:**
  - Consola *serial*: puerto COM, 9600 baudios, 8N1, y el comando de PuTTY. Es el **cable de consola** conectado al PC.
  - Consola *telnet*: la consola del equipo en GNS3/EVE-NG.
  - Gestión remota (SSH o consola) y si las credenciales están configuradas en `.env`.
- **Probar conexión** y **Leer puertos del equipo** (solo equipos reales).
- **Puertos físicos:** vista del frente del equipo con un LED por puerto (verde arriba, rojo abajo, ámbar apagado, gris desconocido; borde azul = fibra). Clic en un puerto para editarlo (IP, VLAN, «conectado a»). El estado cambia solo cuando llega un Syslog de enlace.

**Agregar equipo:** nombre, IP (la que envía Syslog), marca, modelo, consola (tipo, puerto y velocidad), gestión (SSH o consola) y las casillas *lista permitida* y *simulado*. Las claves de los equipos **no** se escriben aquí: van en el archivo `.env`.

### Configuraciones
Elige el fabricante, la IP del NOC, el puerto, la severidad, la facility, el NTP y la interfaz de origen → **Generar** → **Copiar**. Las líneas con `!` o `#` son comentarios explicativos.

### Consola
Elige el equipo y escribe un comando o pulsa uno de la lista permitida. En equipos **reales** el servidor se conecta por SSH o consola; en simulados responde con datos de ejemplo. Los comandos que cambian, borran o reinician el equipo, o que encadenan comandos, se **bloquean**. Todo queda en la auditoría.

### Política IA
Flujo seguro, reglas activas, cuántos eventos marcó cada regla y los parámetros configurados.

### Verificación
- **Controles del sistema:** receptor, hora del servidor (NTP), fechas inmutables, integridad de la auditoría, Telegram y respaldo reciente. Botones **Verificar hora NTP ahora** y **Verificar integridad**.
- **Políticas Syslog por equipo:** lista permitida, si envía Syslog, hora sincronizada, consola documentada, puertos registrados y gestión remota (✔ cumple · ! revisar · ✖ no cumple · – sin datos).
- **Alertas por Telegram:** estado (token enmascarado) e historial. El admin puede **Enviar prueba**.

### Auditoría
Registro de quién hizo qué y cuándo, con el inicio del hash encadenado. No se puede editar ni borrar.

### Usuarios (admin)
**Crear usuario** → usuario, nombre y rol → se muestra la **clave temporal UNA vez** → entrégala por un medio seguro. Desde **Editar** se cambia el rol o se desactiva la cuenta (se revocan sus tokens). **Nueva clave** genera otra clave temporal.

> **Claves para el auditor:** crea el usuario con rol *Auditor* y entrega la clave temporal. El auditor la cambia en su primer ingreso, así nadie más la conoce.

### API
Crea **tokens** para scripts u otras herramientas: se muestran una vez y tienen los permisos de tu rol. Incluye ejemplos y la lista de rutas. Más detalle en `docs/API.md`.
