# Guía de trabajo por fases (para quien sube el proyecto)

Esta guía sirve para subir el proyecto a **tu propio GitHub** con **commits progresivos**, uno por fase, tal como pide el docente. Antes de cada commit **lee los archivos de la fase** y responde con tus palabras la *pregunta de validación*: es lo que te van a preguntar en la sustentación.

---

## 0. Preparar el PC (una sola vez)

1. Instala **Python 3.10+** (marca *Add Python to PATH*) y **Git**.
2. Configura Git **solo para este proyecto** con tu nombre y tu correo de GitHub (así los commits salen a tu nombre aunque el PC sea de otra persona):

```bash
cd noc-syslog-inteligente
git init
git config user.name "Tu Nombre Completo"
git config user.email "tu-correo@ejemplo.com"
git branch -M main
```

> Usa `git config` **sin** `--global`: así solo afecta esta carpeta.

3. En GitHub crea un repositorio **vacío** llamado `noc-syslog-inteligente`, sin README ni .gitignore.
4. Conéctalo:

```bash
git remote add origin https://github.com/TU-USUARIO/noc-syslog-inteligente.git
```

Cuando hagas `git push`, GitHub pedirá iniciar sesión. Si el PC tiene guardada la cuenta de otra persona, en Windows abre **Administrador de credenciales → Credenciales de Windows**, borra la entrada `git:https://github.com` y vuelve a intentarlo.

5. Crea la rama de desarrollo (la rúbrica revisa las ramas):

```bash
git checkout -b desarrollo
```

6. Prepara el entorno:

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env           # Windows   (Linux/macOS: cp .env.example .env)
```

---

## Fase 1: estructura, configuración y modelo de datos

**Archivos:** `requirements.txt`, `.gitignore`, `.env.example`, `config.py`, `noc/__init__.py`, `noc/schema.sql`, `noc/db.py`

**Probar:**

```bash
python -c "from noc import db; c=db.connect('data/noc.db'); db.init_db(c); db.sembrar_si_vacia(c); print(c.execute('SELECT nombre, ip, marca FROM dispositivos').fetchall())"
```

Debe listar 6 equipos simulados.

```bash
git add requirements.txt .gitignore .env.example config.py noc/__init__.py noc/schema.sql noc/db.py
git commit -m "feat(fase1): estructura del proyecto, configuración por .env y modelo de datos SQLite"
git push -u origin desarrollo
```

**Pregunta de validación:** ¿por qué el archivo `.env` está en `.gitignore` y qué pasaría si se subiera a GitHub? ¿Para qué sirve la columna `autorizado` de la tabla `dispositivos`?

---

## Fase 2: motor Syslog (parser y política)

**Archivos:** `noc/syslog_parser.py`, `noc/politica.py`, `tests/conftest.py`, `tests/test_parser.py`, `tests/test_politica.py`

**Probar:**

```bash
python -m pytest -v tests/test_parser.py tests/test_politica.py
```

```bash
git add noc/syslog_parser.py noc/politica.py tests/conftest.py tests/test_parser.py tests/test_politica.py
git commit -m "feat(fase2): parser Syslog multivendor (RFC 5424/3164, Cisco, Fortinet, Huawei) y reglas de política IA"
git push
```

**Pregunta de validación:** si llega `<190>`, ¿cuál es la facility y cuál la severidad? (Pista: 190 ÷ 8.) ¿Por qué la política solo *analiza* el texto del log y nunca lo ejecuta?

---

## Fase 3: backend (ingesta, receptor UDP, API REST)

**Archivos:** `app.py`, `noc/ingesta.py`, `noc/receptor_udp.py`, `noc/simulador.py`, `noc/consola.py`, `noc/catalogo_acciones.py`, `noc/generador_config.py`, `noc/routes/` (todos), `tests/test_seguridad.py`, `tests/test_api.py`

**Probar:**

```bash
python -m pytest -v
python app.py
```

Con la app corriendo abre <http://127.0.0.1:8080/api/estado>: debe responder con la versión y el receptor activo. La interfaz aún no existe; se agrega en la fase 4.

```bash
git add app.py noc/ tests/
git commit -m "feat(fase3): API REST de inventario, eventos, incidentes y acciones; receptor UDP y simulador"
git push
```

**Pregunta de validación:** ¿por qué la IP que autoriza un evento es la del paquete UDP y no el hostname del mensaje? ¿Qué pasa con el 121.º mensaje que llega en un minuto desde la misma IP?

---

## Fase 4: interfaz web → versión alfa v0.1.0

**Archivos:** `templates/index.html`, `static/css/estilos.css`, `static/js/` (todos)

**Probar:**

```bash
python app.py
```

Abre <http://127.0.0.1:8080>, usa el simulador y recorre todas las vistas.

```bash
git add templates/ static/
git commit -m "feat(fase4): interfaz web con panel, eventos, filtros, incidentes, inventario y aprobaciones"
git push
git checkout main
git merge desarrollo
git tag -a v0.1.0 -m "Versión alfa"
git push origin main --tags
git checkout desarrollo
```

**Pregunta de validación:** ¿qué hace la función `esc()` de `comun.js` y qué ataque evita si un log contiene `<script>`?

---

## Fase 5: herramientas de prueba y datos de ejemplo

**Archivos:** `samples/syslog_simulado.log`, `tools/enviar_syslog.py`

**Probar:**

```bash
python app.py
# en otra terminal:
python tools/enviar_syslog.py
```

En la interfaz, importa también `samples/syslog_simulado.log`.

```bash
git add samples/ tools/
git commit -m "feat(fase5): archivo Syslog de ejemplo y script de envío UDP para probar el receptor"
git push
```

**Pregunta de validación:** en la consola, ¿por qué `show version ; reload` se bloquea aunque `show version` esté permitido?

---

## Fase 6: documentación, pruebas y release v0.2.0

**Archivos:** `README.md` (completa tus datos), `docs/`, `GUIA_FASES.md`

```bash
python -m pytest -v
git add README.md docs/ GUIA_FASES.md
git commit -m "docs(fase6): README, requisitos, arquitectura y política de defensa frente a agentes de IA"
git push
git checkout main
git merge desarrollo
git tag -a v0.2.0 -m "MVP Corte 2"
git push origin main --tags
```

Luego, en GitHub: **Releases → Draft a new release → tag v0.2.0**, con una descripción corta de lo incluido.

**Pregunta de validación:** recorre el flujo seguro con un ejemplo real del simulador: ¿quién propone, quién aprueba, por qué no puede ser la misma persona y dónde queda la evidencia?

---

## Capturas para el informe (E01–E12)

| Código | Dónde tomarla |
|--------|---------------|
| E01 | Tu perfil y el repositorio en GitHub |
| E02 | GitHub → Commits (rama `desarrollo`) |
| E03 | `docs/requisitos.md` y el diagrama de `docs/arquitectura.md` |
| E04 | Vista **Inventario** |
| E05 | **Panel general** después de simular |
| E06 | Detalle de un evento (clic en la fila) |
| E07 | **Eventos** con el filtro de severidad aplicado |
| E08 | Detalle de un incidente con notas y cambio de estado |
| E09 | **Configuraciones** de Cisco, Fortinet y Huawei |
| E10 | **Consola** con un comando permitido y uno bloqueado |
| E11 | **Política IA** + evento con «posible inyección» |
| E12 | Resultado de `pytest -v` y el release v0.2.0 en GitHub |

Cada captura lleva su pie: qué muestra, qué requisito demuestra, el resultado, «datos simulados» y «v0.2.0».
