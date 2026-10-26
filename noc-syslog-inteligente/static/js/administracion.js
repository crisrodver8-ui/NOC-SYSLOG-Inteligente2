/* administracion.js - Verificación de políticas, Telegram, usuarios y API (tokens). */

/* ---------------- Verificación ---------------- */
const ICONO_ESTADO = { ok: "✔", advertencia: "!", fallo: "✖", sin_datos: "–" };

function celdaEstado(c) {
  return `<span class="control-estado e-${esc(c.estado)}" title="${esc(c.detalle)}">${ICONO_ESTADO[c.estado] || "?"}</span>`;
}

async function cargarVerificacion() {
  const v = await api("/verificacion");
  document.getElementById("controles-globales").innerHTML = Object.entries(v.globales).map(([nombre, c]) => `
    <div class="control">${celdaEstado(c)}<div><b>${esc(nombre)}</b><div class="kpi-pie">${esc(c.detalle)}</div></div></div>`).join("");
  const columnas = v.equipos.length ? Object.keys(v.equipos[0].chequeos) : [];
  document.getElementById("cab-verificacion").innerHTML =
    `<tr><th>Equipo</th>${columnas.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>`;
  document.getElementById("tabla-verificacion").innerHTML = v.equipos.map((e) => `
    <tr><td class="nw"><b>${esc(e.nombre)}</b>${e.simulado ? '<div class="kpi-pie">simulado</div>' : '<div class="kpi-pie">real</div>'}</td>
    ${columnas.map((c) => `<td>${celdaEstado(e.chequeos[c])} <span class="kpi-pie">${esc(e.chequeos[c].detalle)}</span></td>`).join("")}</tr>`).join("");
  if (puede("supervisor", "auditor")) cargarTelegram().catch(() => {});
  else document.getElementById("estado-telegram").innerHTML = `<p class="kpi-pie">Visible para supervisor, auditor y admin.</p>`;
}

async function cargarTelegram() {
  const t = await api("/telegram");
  const e = t.estadisticas;
  document.getElementById("estado-telegram").innerHTML = `
    <dl class="dl">
      <dt>Estado</dt><dd>${t.configurado ? '<span class="chip estado-activo">Configurado</span>' : '<span class="chip estado-inactivo">Sin configurar</span>'}</dd>
      <dt>Token del bot</dt><dd class="mono">${esc(t.token || "— (TELEGRAM_TOKEN en .env)")}</dd>
      <dt>Chat</dt><dd class="mono">${esc(t.chat_id || "— (TELEGRAM_CHAT_ID en .env)")}</dd>
      <dt>Desde el arranque</dt><dd>${e.enviadas} enviadas · ${e.errores} con error · ${e.omitidas} omitidas (duplicadas o límite)</dd>
    </dl>
    <div class="seccion-titulo">Últimas notificaciones</div>
    <ul class="lista">${t.historial.map((n) => `<li>${chipEstado(n.estado === "enviada" ? "activo" : n.estado === "error" ? "rechazada" : "inactivo", n.estado)}
      <div><div class="titulo">${esc(n.asunto)}</div><div class="sub">${esc(n.detalle)}</div></div><div class="der">${fecha(n.fecha)}</div></li>`).join("")
      || '<li class="vacio">Sin notificaciones todavía.</li>'}</ul>`;
}

document.getElementById("btn-verificar-ntp").addEventListener("click", async () => {
  try {
    const r = await api("/hora/verificar", { metodo: "POST", datos: {} });
    aviso(r.verificado ? `NTP ${r.servidor}: desfase ${r.desfase_ms} ms (${r.sincronizado ? "sincronizado" : "FUERA DE RANGO"})` : r.error,
      r.verificado && r.sincronizado ? "" : "error");
    cargarVerificacion();
  } catch (err) { aviso(err.message, "error"); }
});
document.getElementById("btn-integridad").addEventListener("click", async () => {
  try {
    const r = await api("/integridad");
    aviso(r.integra ? `Auditoría íntegra: ${r.total} registros encadenados` : `¡Auditoría ALTERADA en el registro #${r.fila_alterada}!`,
      r.integra ? "" : "error");
  } catch (err) { aviso(err.message, "error"); }
});
document.getElementById("btn-telegram-prueba").addEventListener("click", async () => {
  try { await api("/telegram/prueba", { metodo: "POST", datos: {} }); aviso("Mensaje de prueba enviado a Telegram"); cargarTelegram(); }
  catch (err) { aviso(err.message, "error"); }
});

/* ---------------- Usuarios (admin) ---------------- */
const ROLES = { admin: "Administrador", supervisor: "Supervisor", operador: "Operador", auditor: "Auditor (solo lectura)" };

function mostrarClaveTemporal(usuario, clave) {
  abrirModal({
    titulo: `Clave temporal de ${usuario}`,
    boton: "Ya la entregué",
    cuerpo: `<div class="aviso violeta">Esta clave <b>solo se muestra ahora</b>. Entrégala al usuario por un medio seguro; deberá cambiarla en su primer ingreso.</div>
      <pre class="comando clave-temporal">${esc(clave)}</pre>
      <button type="button" class="btn btn-chico" id="copiar-temporal">Copiar</button>`,
    alEnviar: async () => {},
  }).querySelector("#copiar-temporal").addEventListener("click", () => copiar(clave));
}

async function cargarUsuarios() {
  if (!puede("admin")) return;
  const lista = await api("/usuarios");
  document.getElementById("tabla-usuarios").innerHTML = lista.map((u) => `
    <tr>
      <td><b>${esc(u.usuario)}</b>${u.usuario === NOC.usuario ? ' <span class="kpi-pie">(tú)</span>' : ""}</td>
      <td>${esc(u.nombre)}</td>
      <td><span class="chip marca-chip">${esc(ROLES[u.rol] || u.rol)}</span></td>
      <td>${!u.activo ? chipEstado("inactivo", "Desactivado") : u.bloqueado_hasta && u.bloqueado_hasta > new Date().toISOString().slice(0, 19)
        ? chipEstado("rechazada", "Bloqueado") : u.debe_cambiar_clave ? chipEstado("propuesta", "Clave temporal") : chipEstado("activo", "Activo")}</td>
      <td class="mono">${fecha(u.ultimo_acceso)}</td>
      <td class="kpi-pie">${fecha(u.creado_en, true)} por ${esc(u.creado_por)}</td>
      <td class="acciones-fila nw">
        <button class="btn btn-chico" data-editar-u="${u.id}">Editar</button>
        <button class="btn btn-chico" data-reset-u="${u.id}" data-nombre="${esc(u.usuario)}">Nueva clave</button></td>
    </tr>`).join("");
  document.getElementById("tabla-usuarios").dataset.json = JSON.stringify(lista);
}

document.getElementById("btn-nuevo-usuario").addEventListener("click", () => {
  abrirModal({
    titulo: "Crear usuario",
    boton: "Crear",
    cuerpo: `<div class="form">
      <div class="campo"><label>Usuario</label><input name="usuario" required placeholder="ej. auditor.externo" pattern="[a-z][a-z0-9._\-]{2,31}"></div>
      <div class="campo"><label>Rol</label><select name="rol">${Object.entries(ROLES).map(([k, v]) =>
        `<option value="${k}" ${k === "operador" ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div class="campo completo"><label>Nombre completo</label><input name="nombre"></div>
      <p class="kpi-pie completo">Minúsculas, números, punto o guion; empieza con letra. Se genera una clave temporal.</p></div>`,
    alEnviar: async (d) => {
      const r = await api("/usuarios", { metodo: "POST", datos: d });
      cargarUsuarios();
      setTimeout(() => mostrarClaveTemporal(d.usuario, r.clave_temporal), 50);
    },
  });
});

document.getElementById("tabla-usuarios").addEventListener("click", async (e) => {
  const lista = JSON.parse(e.currentTarget.dataset.json || "[]");
  const editar = e.target.closest("[data-editar-u]");
  const reset = e.target.closest("[data-reset-u]");
  if (editar) {
    const u = lista.find((x) => x.id === Number(editar.dataset.editarU));
    abrirModal({
      titulo: `Editar ${u.usuario}`,
      cuerpo: `<div class="form">
        <div class="campo completo"><label>Nombre</label><input name="nombre" value="${esc(u.nombre)}"></div>
        <div class="campo"><label>Rol</label><select name="rol">${Object.entries(ROLES).map(([k, v]) =>
          `<option value="${k}" ${k === u.rol ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <label class="casilla"><input type="checkbox" name="activo" ${u.activo ? "checked" : ""}> Cuenta activa</label>
        <p class="kpi-pie completo">Desactivar una cuenta revoca también sus tokens de la API.</p></div>`,
      alEnviar: async (d) => { await api(`/usuarios/${u.id}`, { metodo: "PATCH", datos: d }); aviso("Usuario actualizado"); cargarUsuarios(); },
    });
  }
  if (reset && confirm(`¿Generar una nueva clave temporal para ${reset.dataset.nombre}? Su clave actual dejará de funcionar.`)) {
    try {
      const r = await api(`/usuarios/${reset.dataset.resetU}/restablecer`, { metodo: "POST", datos: {} });
      mostrarClaveTemporal(reset.dataset.nombre, r.clave_temporal);
      cargarUsuarios();
    } catch (err) { aviso(err.message, "error"); }
  }
});

/* ---------------- API ---------------- */
async function cargarApi() {
  const [tokens, indice] = await Promise.all([api("/tokens"), api("/")]);
  document.getElementById("lista-tokens").innerHTML = tokens.map((t) => `
    <li><div><div class="titulo">${esc(t.nombre)} <span class="mono kpi-pie">${esc(t.prefijo)}…</span></div>
      <div class="sub">Creado ${fecha(t.creado_en)} · ${t.expira_en ? "vence " + fecha(t.expira_en, true) : "sin vencimiento"}
      · ${t.ultimo_uso ? "último uso " + fecha(t.ultimo_uso) : "sin uso"}</div></div>
      <div class="der">${t.revocado ? chipEstado("rechazada", "Revocado") : `<button class="btn btn-chico btn-peligro" data-revocar="${t.id}">Revocar</button>`}</div></li>`).join("")
    || '<li class="vacio">No tienes tokens. Crea uno para usar la API desde scripts u otras herramientas.</li>';
  document.getElementById("ejemplo-api").textContent =
    `curl -H "Authorization: Bearer noc_TU_TOKEN" ${location.origin}/api/eventos?severidad=2\n\n` +
    `# PowerShell\nInvoke-RestMethod -Uri ${location.origin}/api/resumen -Headers @{Authorization="Bearer noc_TU_TOKEN"}`;
  document.getElementById("nota-rutas").textContent = `${indice.rutas.length} rutas · v${indice.version}`;
  document.getElementById("tabla-rutas").innerHTML = indice.rutas.flatMap((r) => r.metodos.map((m) => `
    <tr><td><span class="metodo m-${m.toLowerCase()}">${m}</span></td><td class="mono">${esc(r.ruta)}</td><td>${esc(r.descripcion)}</td></tr>`)).join("");
}

document.getElementById("btn-nuevo-token").addEventListener("click", () => {
  abrirModal({
    titulo: "Nuevo token de la API",
    boton: "Crear token",
    cuerpo: `<div class="form">
      <div class="campo completo"><label>Nombre (para qué se usará)</label><input name="nombre" required placeholder="ej. script de reportes"></div>
      <div class="campo"><label>Vigencia</label><select name="dias"><option value="30">30 días</option><option value="90" selected>90 días</option>
        <option value="365">1 año</option><option value="0">Sin vencimiento</option></select></div>
      <p class="kpi-pie completo">El token tendrá los permisos de tu rol (${esc(NOC.rol)}). Solo se mostrará una vez.</p></div>`,
    alEnviar: async (d) => {
      const r = await api("/tokens", { metodo: "POST", datos: { nombre: d.nombre, dias: Number(d.dias) } });
      cargarApi();
      setTimeout(() => {
        abrirModal({
          titulo: "Copia tu token ahora",
          boton: "Listo",
          cuerpo: `<div class="aviso violeta">Este token <b>no se volverá a mostrar</b>. Guárdalo como un secreto (por ejemplo en un .env), nunca en GitHub.</div>
            <pre class="comando clave-temporal">${esc(r.token)}</pre><button type="button" class="btn btn-chico" id="copiar-token">Copiar</button>`,
          alEnviar: async () => {},
        }).querySelector("#copiar-token").addEventListener("click", () => copiar(r.token));
      }, 50);
    },
  });
});

document.getElementById("lista-tokens").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-revocar]");
  if (!b || !confirm("¿Revocar este token? Los scripts que lo usen dejarán de funcionar.")) return;
  try { await api(`/tokens/${b.dataset.revocar}`, { metodo: "DELETE" }); aviso("Token revocado"); cargarApi(); }
  catch (err) { aviso(err.message, "error"); }
});
