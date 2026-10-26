-- =====================================================================
-- Modelo de datos - NOC Syslog Inteligente v1.0.0 (SQLite)
-- Las reglas de inmutabilidad (triggers) están en schema_triggers.sql
-- =====================================================================

-- Versión del esquema (para migraciones y rollback)
CREATE TABLE IF NOT EXISTS esquema_version (
    version         TEXT    NOT NULL,
    aplicada_en     TEXT    NOT NULL
);

-- Usuarios con clave (hash PBKDF2/scrypt, nunca en texto plano) y rol.
CREATE TABLE IF NOT EXISTS usuarios (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario             TEXT    NOT NULL UNIQUE,
    nombre              TEXT    NOT NULL DEFAULT '',
    rol                 TEXT    NOT NULL CHECK (rol IN ('admin','supervisor','operador','auditor')),
    clave_hash          TEXT    NOT NULL,
    activo              INTEGER NOT NULL DEFAULT 1,
    debe_cambiar_clave  INTEGER NOT NULL DEFAULT 1,   -- clave temporal: se cambia en el primer ingreso
    intentos_fallidos   INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta     TEXT,
    ultimo_acceso       TEXT,
    creado_por          TEXT    NOT NULL DEFAULT 'sistema',
    creado_en           TEXT    NOT NULL
);

-- Tokens para la API REST (se guarda solo el hash; el token se muestra una vez).
CREATE TABLE IF NOT EXISTS api_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    nombre          TEXT    NOT NULL,
    prefijo         TEXT    NOT NULL,          -- primeros caracteres, para reconocerlo
    token_hash      TEXT    NOT NULL UNIQUE,
    creado_en       TEXT    NOT NULL,
    expira_en       TEXT,
    ultimo_uso      TEXT,
    revocado        INTEGER NOT NULL DEFAULT 0
);

-- Inventario de equipos de red.
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
    autorizado      INTEGER NOT NULL DEFAULT 1,   -- lista permitida de fuentes Syslog y de gestión
    simulado        INTEGER NOT NULL DEFAULT 1,
    -- Acceso de administración
    gestion         TEXT    NOT NULL DEFAULT 'ninguna' CHECK (gestion IN ('ninguna','ssh','consola')),
    ssh_puerto      INTEGER NOT NULL DEFAULT 22,
    consola_tipo    TEXT    NOT NULL DEFAULT 'ninguna' CHECK (consola_tipo IN ('ninguna','serial','telnet')),
    consola_destino TEXT    NOT NULL DEFAULT '',  -- COM3  ó  127.0.0.1:5000 (GNS3)
    consola_velocidad INTEGER NOT NULL DEFAULT 9600,
    actualizado_en  TEXT    NOT NULL
);

-- Puertos físicos y lógicos de cada equipo.
CREATE TABLE IF NOT EXISTS interfaces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo_id  INTEGER NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
    nombre          TEXT    NOT NULL,
    nombre_norm     TEXT    NOT NULL,          -- nombre normalizado (Gi0/1 = GigabitEthernet0/1)
    tipo            TEXT    NOT NULL DEFAULT 'cobre'
                    CHECK (tipo IN ('cobre','fibra','consola','gestion','virtual')),
    velocidad       TEXT    NOT NULL DEFAULT '',
    estado          TEXT    NOT NULL DEFAULT 'desconocido'
                    CHECK (estado IN ('up','down','admin_down','desconocido')),
    ip              TEXT    NOT NULL DEFAULT '',
    vlan            TEXT    NOT NULL DEFAULT '',
    descripcion     TEXT    NOT NULL DEFAULT '',
    conectado_a     TEXT    NOT NULL DEFAULT '',
    origen          TEXT    NOT NULL DEFAULT 'manual' CHECK (origen IN ('manual','syslog','ssh')),
    actualizado_en  TEXT    NOT NULL,
    UNIQUE (dispositivo_id, nombre_norm)
);

-- Eventos Syslog recibidos, importados o simulados.
CREATE TABLE IF NOT EXISTS eventos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    recibido_en     TEXT    NOT NULL,          -- hora del colector: confiable e inmutable
    fecha_evento    TEXT,                      -- hora que reporta el equipo (dato no confiable)
    ip_origen       TEXT    NOT NULL,
    hostname        TEXT,
    dispositivo_id  INTEGER REFERENCES dispositivos(id) ON DELETE SET NULL,
    marca           TEXT,
    facility        INTEGER NOT NULL,
    facility_nombre TEXT    NOT NULL,
    severidad       INTEGER NOT NULL CHECK (severidad BETWEEN 0 AND 7),
    app             TEXT,
    mensaje         TEXT    NOT NULL,
    crudo           TEXT    NOT NULL,
    formato         TEXT    NOT NULL,
    origen          TEXT    NOT NULL CHECK (origen IN ('udp','importacion','simulador','politica')),
    huella          TEXT    NOT NULL,
    repeticiones    INTEGER NOT NULL DEFAULT 1,
    ultima_vez      TEXT    NOT NULL,
    banderas        TEXT    NOT NULL DEFAULT '',
    sospechoso      INTEGER NOT NULL DEFAULT 0,
    riesgo          INTEGER NOT NULL DEFAULT 0,   -- puntaje 0-100 calculado por la política
    desfase_s       INTEGER                       -- segundos entre hora del equipo y del colector
);
CREATE INDEX IF NOT EXISTS ix_eventos_fecha     ON eventos(recibido_en);
CREATE INDEX IF NOT EXISTS ix_eventos_sev       ON eventos(severidad);
CREATE INDEX IF NOT EXISTS ix_eventos_huella    ON eventos(huella, ultima_vez);
CREATE INDEX IF NOT EXISTS ix_eventos_disp      ON eventos(dispositivo_id);

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

CREATE TABLE IF NOT EXISTS incidente_notas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    incidente_id    INTEGER NOT NULL REFERENCES incidentes(id) ON DELETE CASCADE,
    autor           TEXT    NOT NULL,
    nota            TEXT    NOT NULL,
    creado_en       TEXT    NOT NULL
);

-- Acciones con el flujo seguro (ver noc/routes/acciones.py)
CREATE TABLE IF NOT EXISTS acciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evento_id       INTEGER REFERENCES eventos(id) ON DELETE SET NULL,
    incidente_id    INTEGER REFERENCES incidentes(id) ON DELETE SET NULL,
    dispositivo_id  INTEGER NOT NULL REFERENCES dispositivos(id),
    tipo            TEXT    NOT NULL,
    parametro       TEXT,
    comando         TEXT    NOT NULL,
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

-- Auditoría encadenada: cada fila guarda el hash de la anterior.
-- Si alguien altera una fila, la cadena deja de cuadrar (ver db.verificar_cadena).
CREATE TABLE IF NOT EXISTS auditoria (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           TEXT    NOT NULL,
    usuario         TEXT    NOT NULL,
    rol             TEXT    NOT NULL,
    accion          TEXT    NOT NULL,
    objeto          TEXT    NOT NULL DEFAULT '',
    detalle         TEXT    NOT NULL DEFAULT '',
    hash_anterior   TEXT,
    hash            TEXT
);
CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON auditoria(fecha);

-- Registro de alertas enviadas (Telegram)
CREATE TABLE IF NOT EXISTS notificaciones (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha           TEXT    NOT NULL,
    canal           TEXT    NOT NULL,
    asunto          TEXT    NOT NULL,
    estado          TEXT    NOT NULL CHECK (estado IN ('enviada','error','omitida')),
    detalle         TEXT    NOT NULL DEFAULT ''
);
