/* herramientas.js - Configuraciones, consola simulada, política y auditoría. */

/* ---------------- Configuraciones ---------------- */
document.getElementById("config-nivel").innerHTML = NOC.SEVERIDADES.map((s, i) =>
  `<option value="${i}" ${i === 6 ? "selected" : ""}>0 a ${i} (${s})</option>`).join("");
document.getElementById("config-facility").innerHTML = [0, 1, 2, 3, 4, 5, 6, 7].map((i) =>
  `<option value="${i}" ${i === 7 ? "selected" : ""}>local${i}</option>`).join("");

document.getElementById("form-config").addEventListener("submit", async (e) => {
  e.preventDefault();
  const datos = Object.fromEntries(new FormData(e.target));
  const error = document.getElementById("error-config");
  try {
    const r = await api("/configuraciones", { metodo: "POST", datos });
    // Resalta los comentarios (líneas que empiezan con ! o #)
    document.getElementById("salida-config").innerHTML = r.texto.split("\n").map((l) =>
      /^\s*[!#]/.test(l) ? `<span class="com">${esc(l)}</span>` : esc(l)).join("\n");
    document.getElementById("titulo-config").textContent = `Configuración ${datos.marca}`;
    error.hidden = true;
  } catch (err) { error.textContent = err.message; error.hidden = false; }
});
document.getElementById("btn-copiar").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(document.getElementById("salida-config").textContent);
    aviso("Configuración copiada");
  } catch { aviso("No se pudo copiar; selecciona el texto manualmente.", "error"); }
});

/* ---------------- Consola simulada ---------------- */
let comandosPermitidos = {};
const historial = [];
let posHistorial = 0;

function lineaConsola(html) {
  const salida = document.getElementById("consola-salida");
  salida.insertAdjacentHTML("beforeend", html + "\n");
  salida.scrollTop = salida.scrollHeight;
}

function equipoConsola() {
  return NOC.dispositivos.find((d) => d.id === Number(document.getElementById("consola-equipo").value));
}

function pintarPermitidos() {
  const d = equipoConsola();
  if (!d) return;
  document.getElementById("consola-prompt").textContent = `${d.nombre}#`;
  document.getElementById("consola-info").textContent = `${d.marca} · ${d.ip}${d.autorizado ? "" : " · NO autorizado"}`;
  document.getElementById("consola-permitidos").innerHTML = (comandosPermitidos[d.marca] || [])
    .map((c) => `<button type="button" data-cmd="${esc(c)}">${esc(c)}</button>`).join("");
}

async function cargarConsola() {
  await cargarDispositivos();
  comandosPermitidos = await api("/consola/comandos");
  const sel = document.getElementById("consola-equipo");
  const actual = sel.value;
  sel.innerHTML = opcionesEquipos(actual);
  pintarPermitidos();
  if (!document.getElementById("consola-salida").textContent) {
    lineaConsola(`<span class="sist">NOC Syslog Inteligente - consola simulada de solo lectura.\nEscribe un comando permitido o pulsa uno de la lista.</span>`);
  }
}

async function enviarComando(comando) {
  const d = equipoConsola();
  if (!d || !comando.trim()) return;
  historial.push(comando); posHistorial = historial.length;
  lineaConsola(`<span class="p">${esc(d.nombre)}#</span> ${esc(comando)}`);
  try {
    const r = await api("/consola", { metodo: "POST", datos: { dispositivo_id: d.id, comando } });
    lineaConsola(r.permitido ? esc(r.salida) : `<span class="bloq">✖ ${esc(r.salida)}</span>`);
  } catch (err) { lineaConsola(`<span class="bloq">✖ ${esc(err.message)}</span>`); }
}

document.getElementById("consola-equipo").addEventListener("change", pintarPermitidos);
document.getElementById("form-consola").addEventListener("submit", (e) => {
  e.preventDefault();
  const campo = document.getElementById("consola-comando");
  enviarComando(campo.value);
  campo.value = "";
});
document.getElementById("consola-comando").addEventListener("keydown", (e) => {
  if (e.key === "ArrowUp" && posHistorial > 0) { e.target.value = historial[--posHistorial]; e.preventDefault(); }
  if (e.key === "ArrowDown") { posHistorial = Math.min(historial.length, posHistorial + 1); e.target.value = historial[posHistorial] || ""; }
});
document.getElementById("consola-permitidos").addEventListener("click", (e) => {
  const b = e.target.closest("[data-cmd]");
  if (b) enviarComando(b.dataset.cmd);
});

/* ---------------- Política IA ---------------- */
const REGLAS = [
  ["Fuentes autorizadas", "Solo la IP de origen de un equipo del inventario con «lista permitida» es confiable. El hostname dentro del mensaje no autoriza (se puede falsificar)."],
  ["Logs = datos, nunca instrucciones", "El texto se analiza con patrones fijos. Si contiene órdenes para una IA (\"ignore previous instructions\", \"ejecuta el comando\"...) se marca como posible inyección y se abre un incidente."],
  ["Accesos y cambios", "Se registran logins exitosos, fallidos y cambios de configuración. Cuatro fallos en 5 minutos = fuerza bruta."],
  ["Fuera de horario y cuentas de servicio", "Un acceso o cambio fuera del horario laboral, o hecho por una cuenta tipo svc-, bot-, ai-agent, se marca como sospechoso."],
  ["Deduplicación y control de tormentas", "Mensajes idénticos en la ventana se agrupan (repeticiones). Si una fuente supera el límite por minuto, se descartan los excedentes y se registra una alerta."],
  ["Severidad que genera incidente", "Severidades 0 a 2, inyecciones y fuerza bruta crean incidentes automáticos (sin duplicar si ya hay uno abierto)."],
  ["Lista permitida de comandos", "La consola solo acepta comandos de consulta por fabricante; los que cambian, borran o reinician se bloquean siempre."],
  ["Aprobación humana", "Toda acción sale de un catálogo cerrado, la aprueba un supervisor distinto de quien la propone, se ejecuta solo si está aprobada y se verifica."],
  ["Roles y auditoría", "Operador, supervisor y auditor con permisos distintos. Cada acción queda registrada con usuario, rol, fecha y detalle."],
  ["Hora confiable (NTP)", "Se guarda la hora del colector y la del equipo; las configuraciones generadas incluyen NTP para que coincidan."],
];
const NOMBRES_BANDERA = {
  fuente_no_autorizada: "Fuente no autorizada", posible_inyeccion: "Posible inyección IA",
  fuerza_bruta: "Fuerza bruta", fuera_de_horario: "Fuera de horario", cuenta_servicio: "Cuenta de servicio",
  cambio_config: "Cambios de config.", fallo_autenticacion: "Fallos de login", tormenta: "Tormentas",
};

async function cargarPolitica() {
  const p = await api("/politica");
  document.getElementById("flujo-politica").innerHTML = PASOS.map((x) => `<span class="paso">${x}</span>`).join('<span class="flecha">→</span>');
  document.getElementById("reglas-politica").innerHTML = REGLAS.map(([t, d], i) =>
    `<div class="regla"><span class="regla-n">${i + 1}</span><div><b>${esc(t)}</b><p>${esc(d)}</p></div></div>`).join("");
  const c = p.contadores;
  document.getElementById("contadores-politica").innerHTML =
    Object.entries(p.banderas).map(([k, v]) => `<div class="contador-caja"><b>${v}</b><span>${esc(NOMBRES_BANDERA[k] || k)}</span></div>`).join("")
    + `<div class="contador-caja"><b>${c.duplicados}</b><span>Duplicados agrupados*</span></div>`
    + `<div class="contador-caja"><b>${c.descartados}</b><span>Descartados por tormenta*</span></div>`;
  document.getElementById("parametros-politica").innerHTML = Object.entries(p.parametros).map(([k, v]) =>
    `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") + `<dt>*</dt><dd class="kpi-pie">Contadores desde el último arranque del servidor.</dd>`;
}

/* ---------------- Auditoría ---------------- */
async function cargarAuditoria() {
  const tbody = document.getElementById("tabla-auditoria");
  if (!puede("supervisor", "auditor")) {
    tbody.innerHTML = `<tr><td colspan="7" class="vacio">Tu rol (${esc(NOC.rol)}) no puede ver la auditoría. Cambia a supervisor1 o auditor1.</td></tr>`;
    return;
  }
  const filas = await api("/auditoria");
  tbody.innerHTML = filas.map((a) => `<tr>
    <td>${a.id}</td><td class="mono">${fecha(a.fecha, true)}</td><td>${esc(a.usuario)}</td><td>${esc(a.rol)}</td>
    <td><span class="chip ${/bloqueado|rechaz|tormenta/.test(a.accion) ? "estado-rechazada" : "marca-chip"}">${esc(a.accion)}</span></td>
    <td>${esc(a.objeto)}</td><td><div class="msg" title="${esc(a.detalle)}">${esc(a.detalle)}</div></td></tr>`).join("")
    || `<tr><td colspan="7" class="vacio">Sin registros.</td></tr>`;
}
