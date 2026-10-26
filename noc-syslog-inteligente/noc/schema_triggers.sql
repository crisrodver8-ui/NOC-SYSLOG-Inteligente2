-- =====================================================================
-- Reglas de INMUTABILIDAD (hallazgo del Corte 2: "hora y fecha no modificables")
--
-- La base de datos misma rechaza cualquier intento de cambiar fechas,
-- autores o contenido original, aunque alguien edite la BD directamente
-- con otra herramienta o haya un error en el código.
-- =====================================================================

-- Auditoría: solo se agregan filas. Nunca se modifican ni se borran.
CREATE TRIGGER IF NOT EXISTS auditoria_sin_update
BEFORE UPDATE ON auditoria
BEGIN
    SELECT RAISE(ABORT, 'La auditoría es inmutable');
END;

CREATE TRIGGER IF NOT EXISTS auditoria_sin_delete
BEFORE DELETE ON auditoria
BEGIN
    SELECT RAISE(ABORT, 'La auditoría es inmutable');
END;

-- Eventos: la hora del colector, la hora del equipo y el contenido original no cambian.
CREATE TRIGGER IF NOT EXISTS eventos_campos_inmutables
BEFORE UPDATE ON eventos
WHEN NEW.recibido_en IS NOT OLD.recibido_en
  OR NEW.fecha_evento IS NOT OLD.fecha_evento
  OR NEW.crudo IS NOT OLD.crudo
  OR NEW.mensaje IS NOT OLD.mensaje
  OR NEW.ip_origen IS NOT OLD.ip_origen
  OR NEW.severidad IS NOT OLD.severidad
  OR NEW.facility IS NOT OLD.facility
BEGIN
    SELECT RAISE(ABORT, 'La fecha y el contenido de un evento son inmutables');
END;

CREATE TRIGGER IF NOT EXISTS eventos_sin_delete
BEFORE DELETE ON eventos
BEGIN
    SELECT RAISE(ABORT, 'Los eventos no se borran (retención por respaldos)');
END;

-- La última vez solo puede avanzar en el tiempo (nunca retroceder)
CREATE TRIGGER IF NOT EXISTS eventos_ultima_vez_avanza
BEFORE UPDATE OF ultima_vez ON eventos
WHEN NEW.ultima_vez < OLD.ultima_vez
BEGIN
    SELECT RAISE(ABORT, 'La fecha de última repetición no puede retroceder');
END;

-- Incidentes: fecha de creación, creador y evento de origen fijos
CREATE TRIGGER IF NOT EXISTS incidentes_campos_inmutables
BEFORE UPDATE ON incidentes
WHEN NEW.creado_en IS NOT OLD.creado_en
  OR NEW.creado_por IS NOT OLD.creado_por
  OR NEW.evento_id IS NOT OLD.evento_id AND OLD.evento_id IS NOT NULL AND NEW.evento_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'La fecha de creación y el autor del incidente son inmutables');
END;

-- Notas de seguimiento: solo se agregan
CREATE TRIGGER IF NOT EXISTS notas_sin_update
BEFORE UPDATE ON incidente_notas
BEGIN
    SELECT RAISE(ABORT, 'Las notas de seguimiento son inmutables');
END;

CREATE TRIGGER IF NOT EXISTS notas_sin_delete
BEFORE DELETE ON incidente_notas
WHEN (SELECT COUNT(*) FROM incidentes WHERE id = OLD.incidente_id) > 0
BEGIN
    SELECT RAISE(ABORT, 'Las notas de seguimiento son inmutables');
END;

-- Acciones: lo que se propuso (equipo, tipo, comando, autor, fecha) no cambia
CREATE TRIGGER IF NOT EXISTS acciones_campos_inmutables
BEFORE UPDATE ON acciones
WHEN NEW.creado_en IS NOT OLD.creado_en
  OR NEW.propuesta_por IS NOT OLD.propuesta_por
  OR NEW.comando IS NOT OLD.comando
  OR NEW.tipo IS NOT OLD.tipo
  OR NEW.dispositivo_id IS NOT OLD.dispositivo_id
BEGIN
    SELECT RAISE(ABORT, 'El contenido de una acción propuesta es inmutable');
END;

-- Una acción verificada o rechazada ya no cambia de estado
CREATE TRIGGER IF NOT EXISTS acciones_estado_final
BEFORE UPDATE OF estado ON acciones
WHEN OLD.estado IN ('verificada','rechazada') AND NEW.estado IS NOT OLD.estado
BEGIN
    SELECT RAISE(ABORT, 'La acción ya está en un estado final');
END;

-- Usuarios: la fecha de creación no cambia
CREATE TRIGGER IF NOT EXISTS usuarios_creado_inmutable
BEFORE UPDATE ON usuarios
WHEN NEW.creado_en IS NOT OLD.creado_en OR NEW.usuario IS NOT OLD.usuario
BEGIN
    SELECT RAISE(ABORT, 'El nombre de usuario y su fecha de creación son inmutables');
END;
