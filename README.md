# NOC Syslog Inteligente · v0.2.0 (MVP)

Aplicación de administración de redes que recibe, clasifica y gestiona eventos **Syslog** de equipos Cisco, Fortinet y Huawei. Incluye una **política de defensa frente a acciones de agentes de IA** con aprobación humana obligatoria.

> **Datos SIMULADOS.** Los equipos del inventario inicial y sus IP (rangos de documentación RFC 5737: 198.51.100.0/24 y 203.0.113.0/24) son de laboratorio. La consola y la ejecución de acciones son simuladas en esta versión.

| | |
|---|---|
| **Asignatura** | Administración y Gestión de Redes · 2026-2 |
| **Docente** | Ing. John Harold Pérez Calderón |
| **Estudiante** | _[Nombre completo]_ · _[Identificación]_ · _[Grupo]_ |
| **Versión** | v0.2.0 · Corte 2 (producto mínimo viable) |

## Funciones

- **Inventario editable** con nombre, IP, marca, modelo, versión, ubicación, estado, fecha de actualización y *lista permitida*.
- **Recepción Syslog** por UDP (puerto 5514), **importación** de archivos `.log` y **simulador** con tres escenarios.
- **Clasificación** por equipo, fabricante, fecha, facility y severidad 0-7. Formatos RFC 5424, RFC 3164, Cisco IOS, FortiOS y Huawei VRP.
- **Panel** con KPIs, actividad por hora, distribución por severidad, salud de equipos, alertas e incidentes.
- **Filtros** por fecha, marca, equipo, severidad, texto y sospechosos.
- **Incidentes**: creación (manual o automática), asignación, seguimiento con notas y cierre con solución.
- **Configuraciones comentadas** para Cisco, Fortinet y Huawei (Syslog + NTP + verificación).
- **Consola simulada** de solo lectura con comandos permitidos y bloqueados.
- **Política IA**: fuentes autorizadas, detección de inyección de instrucciones, fuerza bruta, cambios fuera de horario, cuentas de servicio, deduplicación y control de tormentas.
- **Aprobaciones**: flujo evento → validación → propuesta → revisión humana → aprobación → ejecución → verificación → auditoría.
- **Auditoría** de todas las acciones con usuario y rol.

## Requisitos

- Python **3.10 o superior** ([python.org](https://www.python.org/downloads/); en Windows marca *Add Python to PATH*).
- Git.
- Un navegador moderno.

## Instalación desde cero

```bash
git clone https://github.com/<tu-usuario>/noc-syslog-inteligente.git
cd noc-syslog-inteligente

# Entorno virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt

# Configuración (el .env NO se sube a GitHub)
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

## Ejecución

```bash
python app.py
```

- Interfaz: <http://127.0.0.1:8080>
- Receptor Syslog: UDP `0.0.0.0:5514`

Arriba a la derecha se elige el **usuario simulado**: `operador1`, `operador2`, `supervisor1` o `auditor1`.

### Probar rápidamente

1. **Eventos Syslog** → *Simular: tráfico normal* → **Generar**.
2. *Simular: ataque de agente IA* → **Generar**. Revisa los eventos sospechosos y los incidentes automáticos.
3. **Importar archivo .log** → `samples/syslog_simulado.log`.
4. Recepción UDP real (en otra terminal): `python tools/enviar_syslog.py`.
5. **Aprobaciones**: propone una acción como `operador1`, apruébala como `supervisor1` y ejecútala y verifícala como `operador1`.
6. **Consola**: prueba `show version` (permitido) y `configure terminal` (bloqueado).

### Enviar Syslog desde un equipo real o desde GNS3/Packet Tracer

1. Registra el equipo en **Inventario** con la IP desde la que envía los logs y marca *lista permitida*.
2. Genera su configuración en **Configuraciones** con la IP de este PC y el puerto **5514**.
3. Permite el puerto en el firewall de Windows: `netsh advfirewall firewall add rule name="NOC Syslog" dir=in action=allow protocol=UDP localport=5514`.

## Pruebas

```bash
python -m pytest -v
```

27 pruebas: parser, política, seguridad (consola y catálogo) y API de extremo a extremo.

## Estructura

```
noc-syslog-inteligente/
├── app.py                  # Punto de entrada (Flask + receptor UDP)
├── config.py               # Configuración desde .env
├── noc/
│   ├── schema.sql          # Modelo de datos
│   ├── db.py               # SQLite, semilla y auditoría
│   ├── syslog_parser.py    # Parser multivendor
│   ├── politica.py         # Reglas de defensa IA, dedup y tormentas
│   ├── ingesta.py          # Canal único de procesamiento
│   ├── receptor_udp.py     # Hilo receptor UDP
│   ├── simulador.py        # Escenarios simulados
│   ├── generador_config.py # Cisco / Fortinet / Huawei
│   ├── consola.py          # Comandos permitidos y bloqueados
│   ├── catalogo_acciones.py# Acciones de respuesta permitidas
│   └── routes/             # API REST
├── templates/index.html    # Interfaz
├── static/css, static/js   # Estilos y lógica del navegador
├── samples/                # Logs de ejemplo
├── tools/enviar_syslog.py  # Envío UDP de prueba
├── tests/                  # Pruebas automáticas (pytest)
└── docs/                   # Requisitos, arquitectura, política IA
```

## Seguridad

- Sin secretos en el código: todo va en `.env`, que está en `.gitignore`.
- Consultas SQL parametrizadas.
- Los logs se tratan como **datos no confiables**: se escapan en la interfaz y nunca se ejecutan ni se usan como instrucciones. Hay una Content-Security-Policy activa.
- La lista permitida de fuentes usa la IP real del paquete, no el hostname del mensaje.
- Las acciones salen de un catálogo cerrado, las aprueba una persona distinta de quien las propone y quedan auditadas.

Ver [docs/politica_defensa_ia.md](docs/politica_defensa_ia.md).

## Limitaciones de v0.2.0

- Usuarios simulados (sin contraseña), con el usuario en la cabecera `X-Usuario`.
- La consola y la ejecución de acciones son simuladas (no hay SSH).
- Solo Syslog por UDP, sin TLS.
- Sin alertas por Telegram (previstas para v1.0.0).

## Versiones

| Versión | Contenido |
|---------|-----------|
| v0.1.0 | Alfa: modelo de datos, motor Syslog, API e interfaz inicial |
| v0.2.0 | MVP del Corte 2: flujo completo, política IA, pruebas y documentación |
