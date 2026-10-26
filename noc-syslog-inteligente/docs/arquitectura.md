# Arquitectura y modelo de datos (v1.0.0)

## Diagrama de arquitectura

```mermaid
flowchart LR
    subgraph LAB["Laboratorio GNS3 / EVE-NG"]
        C[Cisco IOSv]
        F[FortiGate-VM]
        H[Huawei]
    end
    C & F & H -- "Syslog UDP 5514" --> R[Receptor UDP<br/>receptor_udp.py]
    A[Archivo .log] --> API
    S[Simulador] --> API
    R --> I
    API[API REST Flask + waitress<br/>noc/routes] --> I[Ingestor<br/>ingesta.py]
    I --> P[Parser<br/>syslog_parser.py]
    I --> PO[Política IA + riesgo<br/>politica.py]
    I --> IF[Puertos<br/>interfaces.py]
    I --> DB[(SQLite<br/>triggers de inmutabilidad<br/>auditoría encadenada)]
    I --> T[Telegram<br/>notificador.py]
    API --> DB
    API --> G[Gestor remoto<br/>gestor_remoto.py]
    G -- "SSH (paramiko)" --> C
    G -- "telnet consola GNS3" --> F
    UI[Navegador<br/>sesión + CSRF] --> API
    EXT[Scripts / integraciones<br/>token Bearer] --> API
    NTP[Servidor NTP] -. SNTP .-> HO[hora.py]
    HO --> API
```

## Flujo de un mensaje Syslog

```mermaid
flowchart TD
    M[Mensaje recibido] --> T{¿Supera el límite<br/>por minuto?}
    T -- sí --> D[Descartar + alerta de tormenta]
    T -- no --> PA[Parsear PRI, fecha, host, mensaje]
    PA --> E{¿IP en la lista permitida?}
    E -- no --> B1[fuente_no_autorizada]
    E -- sí --> HR
    B1 --> HR{¿Hora del equipo difiere<br/>más de 5 min del colector?}
    HR -- sí --> B2[hora_desfasada<br/>horario con hora del colector]
    HR -- no --> PO
    B2 --> PO[Reglas: ofuscación, inyección, login,<br/>cambios, horario, cuenta de servicio]
    PO --> CO{¿Cambio de config?}
    CO -- sí --> AP{¿Acción aprobada<br/>en 30 min?}
    AP -- no --> B3[cambio_no_autorizado]
    CO -- sí --> RF{¿5+ cambios en 60 s?}
    RF -- sí --> B4[rafaga_cambios]
    PO --> RI[Riesgo 0-100]
    RI --> DU{¿Igual a uno de<br/>los últimos 60 s?}
    DU -- sí --> RP[+1 repetición]
    DU -- no --> G[Guardar evento + actualizar puerto]
    G --> INC{¿Sev ≤ 2, inyección, fuerza bruta,<br/>cambio no autorizado o ráfaga?}
    INC -- sí --> NI[Incidente automático + Telegram]
    INC -- no --> AL{¿Riesgo ≥ 60?}
    AL -- sí --> TG[Telegram]
```

## Modelo de datos

```mermaid
erDiagram
    usuarios ||--o{ api_tokens : "posee"
    dispositivos ||--o{ interfaces : "tiene puertos"
    dispositivos ||--o{ eventos : "origina"
    dispositivos ||--o{ incidentes : "afecta"
    dispositivos ||--o{ acciones : "recibe"
    eventos ||--o{ incidentes : "dispara"
    incidentes ||--o{ incidente_notas : "seguimiento"
    incidentes ||--o{ acciones : "responde"
    usuarios {
        int id PK
        text usuario UK
        text rol
        text clave_hash
        int activo
        int debe_cambiar_clave
        int intentos_fallidos
        text bloqueado_hasta
    }
    api_tokens {
        int id PK
        int usuario_id FK
        text token_hash UK
        text expira_en
        int revocado
    }
    dispositivos {
        int id PK
        text nombre UK
        text ip UK
        text marca
        text estado
        int autorizado
        int simulado
        text gestion
        int ssh_puerto
        text consola_tipo
        text consola_destino
        int consola_velocidad
    }
    interfaces {
        int id PK
        int dispositivo_id FK
        text nombre
        text nombre_norm
        text tipo
        text estado
        text ip
        text conectado_a
        text origen
    }
    eventos {
        int id PK
        text recibido_en "inmutable"
        text fecha_evento "inmutable"
        text ip_origen
        int severidad
        text mensaje "inmutable"
        text banderas
        int riesgo
        int desfase_s
    }
    incidentes {
        int id PK
        text titulo
        text estado
        text asignado_a
        text creado_en "inmutable"
    }
    incidente_notas {
        int id PK
        int incidente_id FK
        text nota "inmutable"
    }
    acciones {
        int id PK
        int dispositivo_id FK
        text tipo
        text comando "inmutable"
        text estado
        text propuesta_por
        text revisada_por
    }
    auditoria {
        int id PK
        text fecha
        text usuario
        text accion
        text hash_anterior
        text hash
    }
    notificaciones {
        int id PK
        text fecha
        text asunto
        text estado
    }
```

## Módulos

| Módulo | Responsabilidad |
|--------|-----------------|
| `app.py` | Crea la app, cabeceras de seguridad; arranca receptor, Telegram, NTP y waitress |
| `config.py` | Configuración desde `.env` |
| `noc/db.py` | Conexión, migración, semilla con puertos, auditoría encadenada |
| `noc/schema.sql` / `schema_triggers.sql` | Tablas / 11 reglas de inmutabilidad |
| `noc/autenticacion.py` | Claves, bloqueo, clave temporal, tokens |
| `noc/syslog_parser.py` | RFC 5424/3164, Cisco, Fortinet, Huawei |
| `noc/politica.py` | Reglas, ofuscación, riesgo, deduplicación, tormentas |
| `noc/ingesta.py` | Canal único: hora, política, correlación, puertos, incidentes y alertas |
| `noc/interfaces.py` | Normalización y lectura de puertos |
| `noc/gestor_remoto.py` | SSH y consola telnet con listas permitidas |
| `noc/notificador.py` | Telegram |
| `noc/hora.py` | Cliente SNTP |
| `noc/simulador.py` | Escenarios normal, ataque IA (8 técnicas) y tormenta |
| `noc/generador_config.py` | Configuraciones comentadas por fabricante |
| `noc/consola.py` | Lista de comandos permitidos y bloqueados; salidas simuladas |
| `noc/catalogo_acciones.py` | Acciones de respuesta permitidas |
| `noc/routes/*` | API REST: usuarios, dispositivos, eventos, incidentes, acciones, herramientas |
| `static/js/*` | Acceso, panel, eventos, incidentes, aprobaciones, inventario, herramientas, administración |
| `tools/*` | Respaldo, restauración, carga, crear usuario, equipo virtual y envío UDP |

## Severidades Syslog (RFC 5424)

| Código | Nombre | Uso en el NOC |
|--------|--------|---------------|
| 0 | Emergency | Incidente automático + Telegram |
| 1 | Alert | Incidente automático + Telegram |
| 2 | Critical | Incidente automático + Telegram |
| 3 | Error | Cuenta como «crítico» en el panel |
| 4 | Warning | Advertencia |
| 5 | Notice | Normal pero significativo |
| 6 | Informational | Informativo |
| 7 | Debug | Depuración |
