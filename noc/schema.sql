-- =====================================================================
-- Modelo de datos - NOC Syslog Inteligente v0.2.0 (SQLite)
-- =====================================================================

-- Inventario de equipos de red.
-- "autorizado" = el equipo está en la LISTA PERMITIDA de fuentes Syslog.
CREATE TABLE IF NOT EXISTS dispositivos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT    NOT NULL UNIQUE,
    ip              TEXT    NOT NULL UNIQUE,
    marca           TEXT    NOT NULL CHECK (marca IN ('Cisco','Fortinet','Huawei','Otro')),
    modelo          TEXT    NOT NULL DEFAULT '',
    version         TEXT    NOT NULL DEFAULT '',
    ubicacion       TEXT    NOT NULL DEFAULT '',
    estado          TEXT    NOT NULL DEFAULT 'activo'
                    CHECK (estado IN ('activo','inactivo','mantenimiento')),
    autorizado      INTEGER NOT NULL DEFAULT 1,
    simulado        INTEGER NOT NULL DEFAULT 1,
    actualizado_en  TEXT    NOT NULL
);

-- Eventos Syslog recibidos, importados o simulados.
CREATE TABLE IF NOT EXISTS eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recibido_en     TEXT    NOT NULL,          -- hora del colector (confiable)
    fecha_evento    TEXT,                      -- hora que reporta el equipo (depende de NTP)
    ip_origen       TEXT    NOT NULL,
    hostname        TEXT,
    dispositivo_id  INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    marca           TEXT,
    facility        INTEGER NOT NULL,
    facility_nombre TEXT    NOT NULL,
    severidad       INTEGER NOT NULL CHECK (severidad BETWEEN 0 AND 7),
    app             TEXT,
    mensaje         TEXT    NOT NULL,
    crudo           TEXT    NOT NULL,          -- texto original, se muestra siempre escapado
    formato         TEXT    NOT NULL,
    origen          TEXT    NOT NULL CHECK (origen IN ('udp','importacion','simulador','politica')),
    huella          TEXT    NOT NULL,          -- hash para deduplicación
    repeticiones    INTEGER NOT NULL DEFAULT 1,
    ultima_vez      TEXT    NOT NULL,
    banderas        TEXT    NOT NULL DEFAULT '',  -- etiquetas de la política separadas por coma
    sospechoso      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_eventos_fecha     ON eventos(recibido_en);
CREATE INDEX IF NOT EXISTS ix_eventos_sev       ON eventos(severidad);
CREATE INDEX IF NOT EXISTS ix_eventos_huella    ON eventos(huella, ultima_vez);
CREATE INDEX IF NOT EXISTS ix_eventos_disp      ON eventos(dispositivo_id);

-- Incidentes: creación, asignación, seguimiento y cierre.
CREATE TABLE IF NOT EXISTS incidentes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo          TEXT    NOT NULL,
    descripcion     TEXT    NOT NULL DEFAULT '',
    severidad       INTEGER NOT NULL CHECK (severidad BETWEEN 0 AND 7),
    estado          TEXT    NOT NULL DEFAULT 'abierto'
                    CHECK (estado IN ('abierto','en_progreso','resuelto','cerrado')),
    asignado_a      TEXT,
    creado_por      TEXT    NOT NULL,
    evento_id       INTEGER REFERENCES eventos(id) ON DELETE SET NULL,
    dispositivo_id  INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    solucion        TEXT,
    creado_en       TEXT    NOT NULL,
    actualizado_en  TEXT    NOT NULL,
    cerrado_en      TEXT
);

-- Bitácora de seguimiento de cada incidente.
CREATE TABLE IF NOT EXISTS incidente_notas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incidente_id    INTEGER NOT NULL REFERENCES incidentes(id) ON DELETE CASCADE,
    autor           TEXT    NOT NULL,
    nota            TEXT    NOT NULL,
    creado_en       TEXT    NOT NULL
);

-- Acciones de respuesta. Implementan el flujo seguro:
-- evento -> validación -> propuesta -> revisión humana -> aprobación
--        -> ejecución autorizada -> verificación -> auditoría
CREATE TABLE IF NOT EXISTS acciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id       INTEGER REFERENCES eventos(id) ON DELETE SET NULL,
    incidente_id    INTEGER REFERENCES incidentes(id) ON DELETE SET NULL,
    dispositivo_id  INTEGER NOT NULL REFERENCES dispositivos(id),
    tipo            TEXT    NOT NULL,          -- clave del catálogo permitido
    parametro       TEXT,
    comando         TEXT    NOT NULL,          -- generado desde plantilla, nunca desde el log
    justificacion   TEXT    NOT NULL,
    estado          TEXT    NOT NULL DEFAULT 'propuesta'
                    CHECK (estado IN ('propuesta','aprobada','rechazada','ejecutada','verificada')),
    propuesta_por   TEXT    NOT NULL,
    revisada_por    TEXT,
    comentario_revision TEXT,
    ejecutada_por   TEXT,
    resultado       TEXT,
    verificada_por  TEXT,
    verificacion    TEXT,
    creado_en       TEXT    NOT NULL,
    actualizado_en  TEXT    NOT NULL
);

-- Auditoría: quién hizo qué, cuándo y con qué resultado.
CREATE TABLE IF NOT EXISTS auditoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           TEXT    NOT NULL,
    usuario         TEXT    NOT NULL,
    rol             TEXT    NOT NULL,
    accion          TEXT    NOT NULL,
    objeto          TEXT    NOT NULL DEFAULT '',
    detalle         TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON auditoria(fecha);
