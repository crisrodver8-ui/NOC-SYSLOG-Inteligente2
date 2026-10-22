/* incidentes.js - Crear, asignar, dar seguimiento y cerrar incidentes. */

// Transiciones permitidas (igual que en el backend)
const TRANSICIONES = {
  abierto: ["en_progreso", "cerrado"],
  en_progreso: ["resuelto", "abierto"],
  resuelto: ["cerrado", "en_progreso"],
  cerrado: ["en_progreso"],
};

async function cargarIncidentes() {
  const estado = document.getElementById("filtro-incidentes").value;
  const lista = await api("/incidentes" + (estado ? `?estado=${encodeURIComponent(estado)}` : ""));
  document.getElementById("tabla-incidentes").innerHTML = lista.map((i) => `
    <tr class="clic" data-id="${i.id}">
      <td>${i.id}</td>
      <td><b>${esc(i.titulo)}</b><div class="kpi-pie">${i.notas} nota(s) · creado por ${esc(i.creado_por)}</div></td>
      <td>${chipSev(i.severidad)}</td>
      <td>${chipEstado(i.estado)}</td>
      <td>${esc(i.asignado_a || "—")}</td>
      <td>${esc(i.dispositivo || "—")}</td>
      <td class="mono">${fecha(i.actualizado_en)}</td>
    </tr>`).join("") || `<tr><td colspan="7" class="vacio">No hay incidentes en este filtro.</td></tr>`;
}

function nuevoIncidente(previo = {}) {
  abrirModal({
    titulo: "Nuevo incidente",
    boton: "Crear incidente",
    cuerpo: `<div class="form">
      <div class="campo completo"><label>Título</label><input name="titulo" required maxlength="150" value="${esc(previo.titulo || "")}"></div>
      <div class="campo"><label>Severidad</label><select name="severidad">${NOC.SEVERIDADES.map((s, i) =>
        `<option value="${i}" ${i === (previo.severidad ?? 4) ? "selected" : ""}>${i} ${s}</option>`).join("")}</select></div>
      <div class="campo"><label>Asignar a</label><select name="asignado_a">${opcionesUsuarios()}</select></div>
      <div class="campo completo"><label>Equipo</label><select name="dispositivo_id"><option value="">— Ninguno —</option>${opcionesEquipos(previo.dispositivo_id)}</select></div>
      <div class="campo completo"><label>Descripción</label><textarea name="descripcion">${esc(previo.descripcion || "")}</textarea></div>
      <input type="hidden" name="evento_id" value="${esc(previo.evento_id || "")}">
    </div>`,
    alEnviar: async (d) => {
      const r = await api("/incidentes", { metodo: "POST", datos: {
        ...d, severidad: Number(d.severidad),
        dispositivo_id: d.dispositivo_id ? Number(d.dispositivo_id) : null,
        evento_id: d.evento_id ? Number(d.evento_id) : null } });
      aviso(`Incidente #${r.id} creado`);
      irA("incidentes");
    },
  });
}

async function verIncidente(id) {
  const { incidente: i, notas, acciones } = await api(`/incidentes/${id}`);
  const editable = puede("operador", "supervisor");
  const cuerpo = abrirPanel(`Incidente #${i.id}`, `
    <h3>${esc(i.titulo)}</h3>
    <dl class="dl">
      <dt>Estado</dt><dd>${chipEstado(i.estado)}</dd>
      <dt>Severidad</dt><dd>${chipSev(i.severidad)}</dd>
      <dt>Equipo</dt><dd>${esc(i.dispositivo || "—")}</dd>
      <dt>Creado</dt><dd>${fecha(i.creado_en, true)} por ${esc(i.creado_por)}</dd>
      <dt>Evento origen</dt><dd>${i.evento_id ? `<a href="#" id="inc-evento">#${i.evento_id}</a>` : "—"}</dd>
      <dt>Descripción</dt><dd>${esc(i.descripcion || "—")}</dd>
      ${i.solucion ? `<dt>Solución</dt><dd>${esc(i.solucion)}</dd>` : ""}
      ${i.cerrado_en ? `<dt>Cerrado</dt><dd>${fecha(i.cerrado_en, true)}</dd>` : ""}
    </dl>
    ${editable ? `
    <div class="seccion-titulo">Gestión</div>
    <form class="form" id="form-gestion">
      <div class="campo"><label>Asignado a</label><select name="asignado_a">${opcionesUsuarios(i.asignado_a)}</select></div>
      <div class="campo"><label>Cambiar estado</label><select name="estado"><option value="">— Sin cambio —</option>
        ${TRANSICIONES[i.estado].map((e) => `<option value="${e}">${NOC.ESTADOS_INC[e]}</option>`).join("")}</select></div>
      <div class="campo completo"><label>Solución (obligatoria para resolver o cerrar)</label><textarea name="solucion">${esc(i.solucion || "")}</textarea></div>
      <div class="completo acciones-fila"><button class="btn btn-primario">Guardar cambios</button>
        <button type="button" class="btn" id="inc-accion">Proponer acción</button></div>
      <p class="error-form completo" hidden></p>
    </form>` : ""}
    ${acciones.length ? `<div class="seccion-titulo">Acciones vinculadas</div>
      <ul class="lista">${acciones.map((a) => `<li>${chipEstado(a.estado, a.estado)}<div><div class="titulo">#${a.id} ${esc(a.tipo)}</div>
        <div class="sub">propuesta por ${esc(a.propuesta_por)}</div></div></li>`).join("")}</ul>` : ""}
    <div class="seccion-titulo">Seguimiento</div>
    <ul class="linea">${notas.map((n) => `<li>${esc(n.nota)}<div class="quien">${esc(n.autor)} · ${fecha(n.creado_en, true)}</div></li>`).join("")}</ul>
    ${editable ? `<form class="form" id="form-nota"><div class="campo completo"><label>Agregar nota</label><textarea name="nota" required></textarea></div>
      <div class="completo"><button class="btn">Agregar nota</button></div></form>` : ""}`);

  cuerpo.querySelector("#inc-evento")?.addEventListener("click", (e) => { e.preventDefault(); verEvento(i.evento_id); });
  cuerpo.querySelector("#inc-accion")?.addEventListener("click", () => {
    cerrarPanel(); nuevaAccion({ incidente_id: i.id, evento_id: i.evento_id, dispositivo_id: i.dispositivo_id });
  });
  cuerpo.querySelector("#form-gestion")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    const cambios = { asignado_a: d.asignado_a };
    if (d.estado) { cambios.estado = d.estado; cambios.solucion = d.solucion; }
    try {
      await api(`/incidentes/${i.id}`, { metodo: "PATCH", datos: cambios });
      aviso("Incidente actualizado");
      verIncidente(i.id); cargarIncidentes();
    } catch (err) {
      const p = e.target.querySelector(".error-form"); p.textContent = err.message; p.hidden = false;
    }
  });
  cuerpo.querySelector("#form-nota")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api(`/incidentes/${i.id}/notas`, { metodo: "POST", datos: { nota: e.target.nota.value } });
      verIncidente(i.id);
    } catch (err) { aviso(err.message, "error"); }
  });
}

document.getElementById("filtro-incidentes").addEventListener("change", cargarIncidentes);
document.getElementById("btn-nuevo-incidente").addEventListener("click", () => nuevoIncidente());
document.getElementById("tabla-incidentes").addEventListener("click", (e) => {
  const fila = e.target.closest("tr[data-id]");
  if (fila) verIncidente(fila.dataset.id).catch((err) => aviso(err.message, "error"));
});
