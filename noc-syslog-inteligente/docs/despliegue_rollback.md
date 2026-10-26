# Procedimiento de despliegue y rollback (v0.2.0 → v1.0.0)

## 1. Principios
- **Siempre respaldo antes de desplegar.** El respaldo lleva SHA-256 y se verifica.
- Cada versión es una **etiqueta de Git** (`v0.2.0`, `v1.0.0`): volver atrás es cambiar de etiqueta y restaurar el respaldo.
- La v1.0.0 **migra sola** una base de datos de v0.2.0: agrega columnas, encadena la auditoría antigua y activa los triggers. La migración no borra datos.
- Tras la migración, la v0.2.0 puede leer la BD, pero **el rollback correcto es restaurar el respaldo previo**.

## 2. Despliegue (actualizar a v1.0.0)

| # | Paso | Comando | Verificación |
|---|------|---------|--------------|
| 1 | Detener la aplicación | `Ctrl + C` en la terminal | La interfaz deja de responder |
| 2 | Respaldo | `python tools/respaldo.py` | «integridad OK, auditoría encadenada OK». Anota el archivo |
| 3 | Obtener la versión | `git fetch --tags` y `git checkout v1.0.0` | `git describe --tags` muestra `v1.0.0` |
| 4 | Dependencias | `pip install -r requirements.txt` | Instala waitress y paramiko sin errores |
| 5 | Configuración | Compara `.env` con `.env.example` y agrega las variables nuevas (SSH, Telegram, NTP) | — |
| 6 | Pruebas | `python -m pytest -q` | Todas `passed` |
| 7 | Arrancar | `python app.py` | Muestra `v1.0.0`, «Receptor Syslog escuchando» y `Serving on` (waitress) |
| 8 | Configuración inicial | Abre la interfaz y crea el admin; luego los usuarios | Login correcto |
| 9 | Verificación posterior | Vista **Verificación** | Receptor ✔, fechas inmutables ✔, integridad ✔ |
| 10 | Prueba de humo | Simular tráfico normal; consola `show clock` en un equipo real | Eventos visibles; consola responde |

**Criterio de éxito:** los pasos 6, 9 y 10 en verde. Si alguno falla y no se resuelve en 15 minutos, se hace el **rollback**.

## 3. Rollback (volver a v0.2.0)

| # | Paso | Comando |
|---|------|---------|
| 1 | Detener la aplicación | `Ctrl + C` |
| 2 | Conservar evidencia | Copia `data/noc.db` a `data/noc.db.fallida-<fecha>` |
| 3 | Volver al código anterior | `git checkout v0.2.0` |
| 4 | Dependencias anteriores | `pip install -r requirements.txt` |
| 5 | Restaurar la BD previa | `python tools/restaurar.py respaldos/noc-<fecha-del-paso-2-del-despliegue>.db` (verifica el SHA-256 y guarda la BD actual como `.antes-de-restaurar-…`) |
| 6 | Arrancar | `python app.py` | 
| 7 | Verificar | La interfaz muestra `v0.2.0` y los eventos previos al despliegue |

Para **volver a intentar** el despliegue: `git checkout v1.0.0` y repetir desde el paso 4 de la sección 2.

## 4. Rollback de una acción en un equipo (no del software)

Si una **acción aprobada** dejó mal un equipo:
1. Propón la acción **«Restaurar la última configuración respaldada»** para ese equipo (requiere `copy running-config flash:noc-respaldo.cfg` hecho antes, ver `docs/laboratorio_gns3.md`).
2. Un supervisor la aprueba, se ejecuta y se verifica con `show running-config | include logging` o `show archive log config all`.
3. Queda todo en la auditoría.

## 5. Registro de despliegues

| Fecha | Versión origen → destino | Respaldo (archivo y SHA-256) | Pruebas | Resultado | Responsable |
|-------|--------------------------|------------------------------|---------|-----------|-------------|
|  | v0.2.0 → v1.0.0 |  |  |  |  |
|  | Ensayo de rollback v1.0.0 → v0.2.0 |  |  |  |  |
|  | v0.2.0 → v1.0.0 (definitivo) |  |  |  |  |

> Para la sustentación conviene **ensayar el rollback una vez** y dejar la evidencia: capturas de los pasos 3, 5 y 7.
