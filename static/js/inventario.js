/* inventario.js - CRUD de equipos y lista permitida de fuentes Syslog. */

async function cargarInventario() {
  const lista = await cargarDispositivos();
  const editable = puede("operador", "supervisor");
  document.getElementById("tabla-inventario").innerHTML = lista.map((d) => `
    <tr>
      <td><b>${esc(d.nombre)}</b>${d.simulado ? '<div class="kpi-pie">simulado</div>' : ""}</td>
      <td class="mono">${esc(d.ip)}</td>
      <td><span class="chip marca-chip">${esc(d.marca)}</span></td>
      <td>${esc(d.modelo)}</td>
      <td>${esc(d.version)}</td>
      <td>${esc(d.ubicacion)}</td>
      <td>${chipEstado(d.estado, d.estado)}</td>
      <td>${d.autorizado ? '<span class="chip estado-activo">Autorizado</span>' : '<span class="chip estado-rechazada">Bloqueado</span>'}</td>
      <td class="mono">${fecha(d.actualizado_en)}</td>
      <td class="acciones-fila">
        ${editable ? `<button class="btn btn-chico" data-editar="${d.id}">Editar</button>` : ""}
        ${puede("supervisor") ? `<button class="btn btn-chico btn-peligro" data-borrar="${d.id}">Eliminar</button>` : ""}
      </td>
    </tr>`).join("") || `<tr><td colspan="10" class="vacio">Sin equipos.</td></tr>`;
}

function formularioEquipo(d = {}) {
  const sel = (nombre, opciones, actual) => `<select name="${nombre}">${opciones.map((o) =>
    `<option ${o === actual ? "selected" : ""}>${o}</option>`).join("")}</select>`;
  abrirModal({
    titulo: d.id ? `Editar ${d.nombre}` : "Agregar equipo",
    cuerpo: `<div class="form">
      <div class="campo"><label>Nombre</label><input name="nombre" required value="${esc(d.nombre || "")}"></div>
      <div class="campo"><label>IP de gestión / origen Syslog</label><input name="ip" required value="${esc(d.ip || "")}"></div>
      <div class="campo"><label>Marca</label>${sel("marca", ["Cisco", "Fortinet", "Huawei", "Otro"], d.marca)}</div>
      <div class="campo"><label>Modelo</label><input name="modelo" value="${esc(d.modelo || "")}"></div>
      <div class="campo"><label>Versión de software</label><input name="version" value="${esc(d.version || "")}"></div>
      <div class="campo"><label>Estado</label>${sel("estado", ["activo", "inactivo", "mantenimiento"], d.estado || "activo")}</div>
      <div class="campo completo"><label>Ubicación</label><input name="ubicacion" value="${esc(d.ubicacion || "")}"></div>
      <label class="casilla"><input type="checkbox" name="autorizado" ${d.autorizado ?? 1 ? "checked" : ""}> En la lista permitida de fuentes Syslog</label>
      <label class="casilla"><input type="checkbox" name="simulado" ${d.simulado ?? 1 ? "checked" : ""}> Equipo simulado</label>
    </div>`,
    alEnviar: async (datos) => {
      if (d.id) await api(`/dispositivos/${d.id}`, { metodo: "PUT", datos });
      else await api("/dispositivos", { metodo: "POST", datos });
      aviso("Inventario actualizado");
      cargarInventario();
    },
  });
}

document.getElementById("btn-nuevo-equipo").addEventListener("click", () => formularioEquipo());
document.getElementById("tabla-inventario").addEventListener("click", async (e) => {
  const editar = e.target.closest("[data-editar]");
  const borrar = e.target.closest("[data-borrar]");
  if (editar) formularioEquipo(NOC.dispositivos.find((d) => d.id === Number(editar.dataset.editar)));
  if (borrar) {
    const d = NOC.dispositivos.find((x) => x.id === Number(borrar.dataset.borrar));
    if (!confirm(`¿Eliminar ${d.nombre}? Sus eventos se conservan sin equipo asociado.`)) return;
    try { await api(`/dispositivos/${d.id}`, { metodo: "DELETE" }); aviso("Equipo eliminado"); cargarInventario(); }
    catch (err) { aviso(err.message, "error"); }
  }
});
