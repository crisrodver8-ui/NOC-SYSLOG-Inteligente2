/* resumen.js - Panel general (KPIs, gráficos, salud de equipos, alertas). */

const ICONOS = {
  equipo: '<svg viewBox="0 0 24 24"><rect x="2" y="4" width="20" height="6" rx="1"/><rect x="2" y="14" width="20" height="6" rx="1"/></svg>',
  evento: '<svg viewBox="0 0 24 24"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>',
  critico: '<svg viewBox="0 0 24 24"><path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/></svg>',
  sospechoso: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/></svg>',
  incidente: '<svg viewBox="0 0 24 24"><path d="M4 4h16v12H8l-4 4z"/></svg>',
  aprobacion: '<svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="9"/></svg>',
};

function tarjetaKpi(icono, tono, titulo, valor, pie) {
  return `<div class="tarjeta kpi">
    <div class="kpi-cab"><span class="kpi-icono ${tono}">${ICONOS[icono]}</span>${esc(titulo)}</div>
    <div class="kpi-valor">${esc(valor)}</div>
    <div class="kpi-pie">${esc(pie)}</div></div>`;
}

async function cargarResumen() {
  const r = await api("/resumen");
  const k = r.kpis;
  const porEstado = k.equipos_por_estado;
  document.getElementById("kpis").innerHTML = [
    tarjetaKpi("equipo", "t-primario", "Equipos", k.equipos,
      `${porEstado.activo || 0} activos · ${porEstado.mantenimiento || 0} mant. · ${porEstado.inactivo || 0} inact.`),
    tarjetaKpi("evento", "t-exito", "Eventos 24 h", k.eventos_24h, `${k.mensajes_24h} mensajes (con duplicados) · ${k.eventos_1h} última hora`),
    tarjetaKpi("critico", "t-peligro", "Severidad 0-3", k.criticos_24h, "Emergency a Error en 24 h"),
    tarjetaKpi("sospechoso", "t-violeta", "Sospechosos", k.sospechosos_24h, `${k.no_autorizados} fuente(s) no autorizada(s)`),
    tarjetaKpi("incidente", "t-alerta", "Incidentes activos", k.incidentes_activos, `${k.incidentes_total} registrados en total`),
    tarjetaKpi("aprobacion", "t-neutro", "Por aprobar", k.acciones_pendientes, "acciones esperando revisión humana"),
  ].join("");

  // Gráfico de columnas: actividad por hora
  const max = Math.max(1, ...r.por_hora.map((h) => h.n));
  const horas = document.getElementById("grafico-horas");
  horas.innerHTML = r.por_hora.map((h) => `
    <div class="columna" title="${esc(h.hora)}: ${h.n} eventos">
      <span class="num">${h.n || ""}</span>
      <div class="barra-v ${h.n ? "" : "cero"}" data-alto="${(h.n / max) * 100}"></div>
      <span class="eje">${esc(h.hora.slice(0, 2))}</span></div>`).join("");
  // La altura se asigna por JS (la política CSP no permite estilos en línea en el HTML)
  horas.querySelectorAll(".barra-v").forEach((b) => { b.style.height = `calc(${b.dataset.alto}% - 34px)`; });

  // Barra apilada + leyenda por severidad
  const total = Object.values(r.por_severidad).reduce((a, b) => a + b, 0);
  const barra = document.getElementById("barra-sev");
  barra.innerHTML = NOC.SEVERIDADES.map((_, i) =>
    r.por_severidad[i] ? `<span data-sev="${i}" title="${esc(NOC.SEVERIDADES[i])}: ${r.por_severidad[i]}"></span>` : "").join("");
  barra.querySelectorAll("span").forEach((s) => {
    const i = s.dataset.sev;
    s.style.width = `${(r.por_severidad[i] / total) * 100}%`;
    s.style.background = `var(--s${i})`;
  });
  document.getElementById("leyenda-sev").innerHTML = NOC.SEVERIDADES.map((_, i) =>
    `<div>${chipSev(i)}<b>${r.por_severidad[i] || 0}</b></div>`).join("");

  // Salud de los equipos
  document.getElementById("lista-equipos").innerHTML = r.equipos.map((d) => {
    const color = d.estado !== "activo" ? "gris" : d.criticos ? "rojo" : d.sospechosos ? "ambar" : "verde";
    return `<li><span class="salud ${color}"></span>
      <div><div class="titulo">${esc(d.nombre)}</div>
      <div class="sub">${esc(d.ip)} · ${esc(d.marca)} · ${esc(d.estado)}${d.autorizado ? "" : " · NO autorizado"}</div></div>
      <div class="der">${d.eventos} eventos · ${d.criticos || 0} críticos<br>${d.ultimo ? "último " + fecha(d.ultimo) : "sin eventos"}</div></li>`;
  }).join("") || `<li class="vacio">Sin equipos en el inventario.</li>`;

  // Alertas recientes
  document.getElementById("lista-alertas").innerHTML = r.criticos.map((e) => `
    <li class="clic-evento" data-id="${e.id}">${chipSev(e.severidad)}
      <div><div class="titulo">${esc(e.equipo)}</div><div class="sub msg">${esc(e.mensaje)}</div></div>
      <div class="der">${fecha(e.recibido_en)}${e.sospechoso ? '<br><span class="chip bandera">sospechoso</span>' : ""}</div></li>`).join("")
    || `<li class="vacio">Sin alertas. Usa el simulador en «Eventos Syslog».</li>`;

  // Incidentes activos
  document.getElementById("lista-incidentes-res").innerHTML = r.incidentes.map((i) => `
    <li class="clic-incidente" data-id="${i.id}">${chipSev(i.severidad)}
      <div><div class="titulo">#${i.id} ${esc(i.titulo)}</div><div class="sub">${esc(i.asignado_a || "sin asignar")}</div></div>
      <div class="der">${chipEstado(i.estado)}</div></li>`).join("")
    || `<li class="vacio">No hay incidentes activos.</li>`;

  actualizarContadores(k.incidentes_activos, k.acciones_pendientes);
}

function actualizarContadores(incidentes, acciones) {
  const ci = document.getElementById("cont-incidentes");
  const ca = document.getElementById("cont-acciones");
  ci.textContent = incidentes; ci.hidden = !incidentes;
  ca.textContent = acciones; ca.hidden = !acciones;
}

document.getElementById("vista-resumen").addEventListener("click", (e) => {
  const ev = e.target.closest(".clic-evento");
  if (ev) verEvento(ev.dataset.id);
  const inc = e.target.closest(".clic-incidente");
  if (inc) verIncidente(inc.dataset.id);
});
