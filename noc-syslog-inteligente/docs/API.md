# API REST · NOC Syslog Inteligente v1.0.0

URL base: `http://127.0.0.1:8080/api`
Índice automático (rutas, métodos y descripción): `GET /api/`

## Autenticación

1. Inicia sesión en la interfaz → vista **API** → **+ Nuevo token**. El token se muestra **una sola vez**.
2. Envíalo en cada petición:

```
Authorization: Bearer noc_XXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

- El token tiene **los mismos permisos que el rol** del usuario que lo creó (un auditor solo puede leer).
- Vence según la vigencia elegida (30, 90 o 365 días, o sin vencimiento) y se puede **revocar**.
- En la BD solo se guarda su hash SHA-256. Si se desactiva el usuario, se revocan sus tokens.
- Respuestas de error: `{"error": "mensaje"}` con código 400 (datos inválidos), 401 (sin autenticar), 403 (rol sin permiso), 404, 409 (duplicado) o 502 (el equipo no respondió).

## Ejemplos

**curl (Git Bash / Linux)**
```bash
TOKEN=noc_xxx
curl -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8080/api/eventos?severidad=2&limite=20"
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"titulo":"Caída del enlace WAN","severidad":2,"asignado_a":"operador1"}' \
     http://127.0.0.1:8080/api/incidentes
```

**PowerShell**
```powershell
$h = @{ Authorization = "Bearer noc_xxx" }
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/resumen" -Headers $h
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/consola" -Headers $h `
  -ContentType "application/json" -Body '{"dispositivo_id":1,"comando":"show clock"}'
```

**Python**
```python
import requests
h = {"Authorization": "Bearer noc_xxx"}
eventos = requests.get("http://127.0.0.1:8080/api/eventos", params={"sospechoso": 1}, headers=h).json()
```

## Rutas principales

| Método | Ruta | Rol mínimo | Descripción |
|--------|------|-----------|-------------|
| GET | `/api/estado` | público | Versión, receptor y verificación NTP |
| GET | `/api/` | público | Índice de rutas |
| GET | `/api/resumen` | cualquiera | KPIs y datos del panel |
| GET | `/api/eventos` | cualquiera | Filtros: `desde`, `hasta` (AAAA-MM-DD), `marca`, `dispositivo_id`, `severidad`, `sev_max`, `riesgo_min`, `sospechoso=1`, `texto`, `limite`, `desplazamiento` |
| GET | `/api/eventos/{id}` | cualquiera | Detalle con el mensaje original |
| POST | `/api/eventos/importar` | operador | multipart `archivo` (.log/.txt) |
| POST | `/api/simulador` | operador | `{"escenario": "normal" \| "ataque_ia" \| "tormenta", "cantidad": 30}` |
| GET/POST | `/api/dispositivos` | cualquiera / operador | Inventario |
| GET/PUT/DELETE | `/api/dispositivos/{id}` | cualquiera / operador / supervisor | Detalle con puertos; editar; eliminar |
| POST | `/api/dispositivos/{id}/interfaces` | operador | Agregar puerto |
| PUT/DELETE | `/api/interfaces/{id}` | operador | Editar o eliminar puerto |
| POST | `/api/dispositivos/{id}/interfaces/sincronizar` | operador | Lee los puertos del equipo real |
| POST | `/api/dispositivos/{id}/probar` | operador | Prueba la conexión SSH/consola |
| GET/POST | `/api/incidentes` | cualquiera / operador | `?estado=activos` |
| GET/PATCH | `/api/incidentes/{id}` | cualquiera / operador | `{"asignado_a", "estado", "solucion"}` |
| POST | `/api/incidentes/{id}/notas` | operador | `{"nota"}` |
| GET | `/api/acciones/catalogo` | cualquiera | Acciones permitidas |
| GET/POST | `/api/acciones` | cualquiera / operador | Proponer: `{"dispositivo_id", "tipo", "parametro", "justificacion"}` |
| POST | `/api/acciones/{id}/revisar` | supervisor | `{"decision": "aprobar" \| "rechazar", "comentario"}` |
| POST | `/api/acciones/{id}/ejecutar` | operador | Solo si está aprobada |
| POST | `/api/acciones/{id}/verificar` | operador | `{"verificacion", "exito"}` |
| POST | `/api/consola` | operador | `{"dispositivo_id", "comando"}`: solo comandos de la lista permitida |
| POST | `/api/configuraciones` | cualquiera | `{"marca", "servidor", "puerto", "protocolo", "nivel", "facility", "ntp", "interfaz", "zona"}` |
| GET | `/api/politica` | cualquiera | Parámetros y contadores de la política |
| GET | `/api/verificacion` | cualquiera | Verificación de políticas por equipo y controles globales |
| POST | `/api/hora/verificar` | supervisor | Consulta NTP ahora |
| GET | `/api/integridad` | auditor / supervisor | Verifica la cadena de la auditoría |
| GET | `/api/auditoria` | auditor / supervisor | `?limite=200` |
| GET | `/api/telegram` | auditor / supervisor | Estado (token enmascarado) e historial |
| POST | `/api/telegram/prueba` | admin | Mensaje de prueba |
| GET/POST | `/api/usuarios` | admin | Listar / crear (devuelve `clave_temporal` una vez) |
| PATCH | `/api/usuarios/{id}` | admin | `{"rol", "activo", "nombre"}` |
| POST | `/api/usuarios/{id}/restablecer` | admin | Nueva clave temporal |
| GET/POST | `/api/tokens` | cualquiera | Mis tokens / crear `{"nombre", "dias"}` |
| DELETE | `/api/tokens/{id}` | dueño o admin | Revocar |

Las rutas `/api/sesion/*` (login, logout, cambio de clave) son para la interfaz web: usan la cookie de sesión y la cabecera anti-CSRF `X-NOC: 1`.
