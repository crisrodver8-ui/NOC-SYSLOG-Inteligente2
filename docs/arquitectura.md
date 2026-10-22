# Arquitectura y modelo de datos (v0.2.0)

## Diagrama de arquitectura

```mermaid
flowchart LR
    subgraph Red["Equipos de red (simulados)"]
        C[Cisco IOS-XE]
        F[FortiGate]
        H[Huawei VRP]
    end
    C & F & H -- "Syslog UDP 5514" --> R[Receptor UDP<br/>receptor_udp.py]
    A[Archivo .log] -- importación --> API
    S[Simulador] --> API
    R --> I
    API[API REST Flask<br/>noc/routes] --> I[Ingestor<br/>ingesta.py]
    I --> P[Parser<br/>syslog_parser.py]
    I --> PO[Política IA<br/>politica.py]
    I --> DB[(SQLite<br/>data/noc.db)]
    API --> DB
    UI[Navegador<br/>HTML + CSS + JS] -- "fetch + X-Usuario" --> API
```

## Flujo de un mensaje Syslog

```mermaid
flowchart TD
    M[Mensaje recibido] --> T{¿Supera el límite<br/>por minuto?}
    T -- sí --> D[Descartar + alerta de tormenta]
    T -- no --> PA[Parsear PRI, fecha, host, mensaje]
    PA --> E{¿IP en la lista permitida?}
    E -- no --> B1[bandera: fuente_no_autorizada]
    E -- sí --> PO
    B1 --> PO[Aplicar reglas: inyección, login,<br/>cambios, horario, cuenta de servicio]
    PO --> DU{¿Igual a uno de<br/>los últimos 60 s?}
    DU -- sí --> RP[+1 repetición]
    DU -- no --> G[Guardar evento]
    G --> INC{¿Severidad ≤ 2, inyección<br/>o fuerza bruta?}
    INC -- sí --> NI[Incidente automático]
    INC -- no --> FIN[Fin]
```

## Modelo de datos

```mermaid
erDiagram
    dispositivos ||--o{ eventos : "origina"
    dispositivos ||--o{ incidentes : "afecta"
    dispositivos ||--o{ acciones : "recibe"
    eventos ||--o{ incidentes : "dispara"
    incidentes ||--o{ incidente_notas : "seguimiento"
    incidentes ||--o{ acciones : "responde"
    dispositivos {
        int id PK
        text nombre UK
        text ip UK
        text marca
        text modelo
        text version
        text ubicacion
        text estado
        int autorizado
        int simulado
        text actualizado_en
    }
    eventos {
        int id PK
        text recibido_en
        text fecha_evento
        text ip_origen
        int dispositivo_id FK
        int facility
        int severidad
        text mensaje
        text crudo
        text huella
        int repeticiones
        text banderas
        int sospechoso
    }
    incidentes {
        int id PK
        text titulo
        int severidad
        text estado
        text asignado_a
        int evento_id FK
        text solucion
    }
    incidente_notas {
        int id PK
        int incidente_id FK
        text autor
        text nota
    }
    acciones {
        int id PK
        int dispositivo_id FK
        text tipo
        text comando
        text estado
        text propuesta_por
        text revisada_por
        text ejecutada_por
        text verificada_por
    }
    auditoria {
        int id PK
        text fecha
        text usuario
        text rol
        text accion
        text detalle
    }
```

## Módulos

| Módulo | Responsabilidad |
|--------|-----------------|
| `app.py` | Crea la aplicación, cabeceras de seguridad y arranca el receptor |
| `config.py` | Lee la configuración desde `.env` |
| `noc/db.py` | Conexión SQLite, esquema, datos semilla y auditoría |
| `noc/syslog_parser.py` | RFC 5424, RFC 3164, Cisco, Fortinet y Huawei |
| `noc/politica.py` | Reglas de detección, deduplicación y control de tormentas |
| `noc/ingesta.py` | Canal único de procesamiento de mensajes |
| `noc/receptor_udp.py` | Hilo que escucha UDP |
| `noc/simulador.py` | Escenarios normal, ataque IA y tormenta |
| `noc/generador_config.py` | Configuraciones comentadas por fabricante |
| `noc/consola.py` | Listas de comandos permitidos y bloqueados |
| `noc/catalogo_acciones.py` | Catálogo cerrado de acciones de respuesta |
| `noc/routes/*` | API REST por módulo |
| `static/js/*` | Una vista por archivo |

## Severidades Syslog (RFC 5424)

| Código | Nombre | Uso en el NOC |
|--------|--------|---------------|
| 0 | Emergency | Sistema inutilizable → incidente automático |
| 1 | Alert | Acción inmediata → incidente automático |
| 2 | Critical | Condición crítica → incidente automático |
| 3 | Error | Cuenta como «crítico» en el panel |
| 4 | Warning | Advertencia |
| 5 | Notice | Normal pero significativo |
| 6 | Informational | Informativo |
| 7 | Debug | Depuración |
