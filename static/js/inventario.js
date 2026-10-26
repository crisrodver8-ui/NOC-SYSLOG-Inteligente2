/* inventario.js - Equipos, acceso de administración (consola/SSH) y puertos físicos. */

const TIPOS_PUERTO = { cobre: "Cobre (RJ45)", fibra: "Fibra (SFP)", consola: "Consola", gestion: "Gestión (OOB)", virtual: "Virtual" };
const ESTADOS_PUERTO = { up: "Arriba", down: "Abajo", admin_down: "Apagado (shutdown)", desconocido: "Desconocido" };

function textoConsola(d) {
  if (d.consola_tipo === "serial") return `Serial ${d.consola_destino} · ${d.consola_velocidad} 8N1`;
  if (d.consola_tipo === "telnet") return `Telnet ${d.consola_destino}`;
  return "—";
}

function textoGestion(d) {
  if (d.simulado) return '<span class="chip estado-inactivo">Simulado</span>';
  return { ssh: `<span class="chip estado-activo">SSH :${d.ssh_puerto}</span>`,
           consola: '<span class="chip estado-mantenimiento">Consola</span>' }[d.gestion] || '<span class="chip estado-inactivo">No</span>';
}

async function cargarInventario() {
  const lista = await cargarDispositivos();
  document.getElementById("tabla-inventario").innerHTML = lista.map((d) => `
    <tr class="clic" data-id="${d.id}">
      <td class="nw"><b>${esc(d.nombre)}</b></td>
      <td class="mono nw">${esc(d.ip)}</td>
      <td><span class="chip marca-chip">${esc(d.marca)}</span></td>
      <td>${esc(d.modelo)}<div class="kpi-pie">${esc(d.version)}</div></td>
      <td>${esc(d.ubicacion)}</td>
      <td>${chipEstado(d.estado, d.estado)}</td>
      <td class="mono nw">${esc(textoConsola(d))}</td>
      <td>${textoGestion(d)}</td>
      <td class="nw">${d.puertos ? `<b>${d.puertos_up}</b>/${d.puertos} arriba` : "—"}</td>
      <td>${d.autorizado ? '<span class="chip estado-activo">Autorizado</span>' : '<span class="chip estado-rechazada">Bloqueado</span>'}</td>
      <td class="mono nw">${fecha(d.actualizado_en)}</td>
    </tr>`).join("") || `<tr><td colspan="11" class="vacio">Sin equipos.</td></tr>`;
}

/* ---------------------------------------------------- formulario de equipo */
function formularioEquipo(d = {}) {
  const sel = (nombre, opciones, actual) => `<select name="${nombre}">${Object.entries(opciones).map(([v, t]) =>
    `<option value="${v}" ${String(v) === String(actual) ? "selected" : ""}>${t}</option>`).join("")}</select>`;
  const lista = (arr) => Object.fromEntries(arr.map((x) => [x, x]));
  const modal = abrirModal({
    titulo: d.id ? `Editar ${d.nombre}` : "Agregar equipo",
    cuerpo: `<div class="form">
      <div class="campo"><label>Nombre</label><input name="nombre" required value="${esc(d.nombre || "")}"></div>
      <div class="campo"><label>IP de gestión / origen Syslog</label><input name="ip" required value="${esc(d.ip || "")}"></div>
      <div class="campo"><label>Marca</label>${sel("marca", lista(["Cisco", "Fortinet", "Huawei", "Otro"]), d.marca)}</div>
      <div class="campo"><label>Modelo</label><input name="modelo" value="${esc(d.modelo || "")}"></div>
      <div class="campo"><label>Versión de software</label><input name="version" value="${esc(d.version || "")}"></div>
      <div class="campo"><label>Estado</label>${sel("estado", lista(["activo", "inactivo", "mantenimiento"]), d.estado || "activo")}</div>
      <div class="campo completo"><label>Ubicación</label><input name="ubicacion" value="${esc(d.ubicacion || "")}"></div>
      <div class="seccion-titulo completo">Puerto de consola (cable de consola)</div>
      <div class="campo"><label>Tipo de consola</label>${sel("consola_tipo", { ninguna: "Ninguna", serial: "Serial (cable RJ45-DB9 / USB)", telnet: "Telnet (GNS3 / EVE-NG)" }, d.consola_tipo || "ninguna")}</div>
      <div class="campo"><label>Puerto o destino</label><input name="consola_destino" value="${esc(d.consola_destino || "")}" placeholder="COM3  ó  127.0.0.1:5000"></div>
      <div class="campo"><label>Velocidad (baudios)</label>${sel("consola_velocidad", lista([9600, 19200, 38400, 57600, 115200]), d.consola_velocidad || 9600)}</div>
      <div class="seccion-titulo completo">Gestión remota desde el servidor</div>
      <div class="campo"><label>Método</label>${sel("gestion", { ninguna: "Ninguna", ssh: "SSH (recomendado)", consola: "Consola telnet (solo laboratorio)" }, d.gestion || "ninguna")}</div>
      <div class="campo"><label>Puerto SSH</label><input name="ssh_puerto" type="number" min="1" max="65535" value="${esc(d.ssh_puerto || 22)}"></div>
      <label class="casilla"><input type="checkbox" name="autorizado" ${d.autorizado ?? 1 ? "checked" : ""}> En la lista permitida</label>
      <label class="casilla"><input type="checkbox" name="simulado" ${d.simulado ?? 1 ? "checked" : ""}> Equipo simulado (sin conexión real)</label>
      <p class="kpi-pie completo">Las credenciales SSH/consola NO se guardan aquí: van en el archivo .env (SSH_USUARIO, SSH_CLAVE o SSH_CLAVE_${esc((d.nombre || "NOMBRE").toUpperCase().replace(/[^A-Z0-9]/g, "_"))}).</p>
    </div>`,
    alEnviar: async (datos) => {
      if (d.id) await api(`/dispositivos/${d.id}`, { metodo: "PUT", datos });
      else await api("/dispositivos", { metodo: "POST", datos });
      aviso("Inventario actualizado");
      await cargarInventario();
      if (d.id) verEquipo(d.id);
    },
  });
  // Sugerencia de velocidad/destino según el tipo de consola
  modal.querySelector('[name="consola_tipo"]').addEventListener("change", (e) => {
    const destino = modal.querySelector('[name="consola_destino"]');
    destino.placeholder = e.target.value === "serial" ? "COM3" : e.target.value === "telnet" ? "127.0.0.1:5000" : "";
  });
}

/* ---------------------------------------------------- detalle del equipo */
async function verEquipo(id) {
  const d = await api(`/dispositivos/${id}`);
  const escribe = puede("operador");
  const real = !d.simulado && d.gestion !== "ninguna";
  const fisicos = d.interfaces.filter((p) => p.tipo === "cobre" || p.tipo === "fibra");
  const especiales = d.interfaces.filter((p) => !(p.tipo === "cobre" || p.tipo === "fibra"));
  const cuerpo = abrirPanel(d.nombre, `
    <dl class="dl">
      <dt>IP / marca</dt><dd class="mono">${esc(d.ip)} · ${esc(d.marca)} ${esc(d.modelo)}</dd>
      <dt>Versión</dt><dd>${esc(d.version || "—")}</dd>
      <dt>Ubicación</dt><dd>${esc(d.ubicacion || "—")}</dd>
      <dt>Estado</dt><dd>${chipEstado(d.estado, d.estado)} ${d.autorizado ? '<span class="chip estado-activo">Lista permitida</span>' : '<span class="chip estado-rechazada">Bloqueado</span>'}</dd>
      <dt>Actualizado</dt><dd>${fecha(d.actualizado_en, true)} (lo fija el servidor)</dd>
    </dl>

    <div class="seccion-titulo">Acceso de administración</div>
    <div class="accesos">
      <div class="acceso-item">
        <span class="acceso-icono">${ICONO_CONSOLA}</span>
        <div><b>Consola</b><div class="sub">${d.consola_tipo === "serial"
          ? `Cable de consola en <b>${esc(d.consola_destino)}</b> · ${d.consola_velocidad} baudios, 8 bits, sin paridad, 1 bit de parada (8N1), sin control de flujo`
          : d.consola_tipo === "telnet" ? `Consola de GNS3/EVE-NG en <b>${esc(d.consola_destino)}</b> (telnet)` : "Sin consola registrada"}</div>
          ${d.consola_tipo === "serial" ? `<div class="mono kpi-pie">PuTTY: putty -serial ${esc(d.consola_destino)} -sercfg ${d.consola_velocidad},8,n,1,N</div>` : ""}
          ${d.consola_tipo === "telnet" ? `<div class="mono kpi-pie">PuTTY: putty -telnet ${esc(d.consola_destino.replace(":", " -P "))}</div>` : ""}</div>
      </div>
      <div class="acceso-item">
        <span class="acceso-icono">${ICONO_SSH}</span>
        <div><b>Gestión remota</b><div class="sub">${d.simulado ? "Equipo simulado: la consola del NOC responde con datos de ejemplo."
          : d.gestion === "ssh" ? `SSH a ${esc(d.ip)}:${d.ssh_puerto} desde el servidor`
          : d.gestion === "consola" ? `Telnet a la consola ${esc(d.consola_destino)} desde el servidor` : "No habilitada"}</div>
          ${real ? `<div class="kpi-pie">Credenciales en .env: ${d.credenciales_configuradas ? "configuradas ✔" : "<b>faltan</b> (SSH_USUARIO / SSH_CLAVE)"}</div>` : ""}</div>
      </div>
    </div>
    ${escribe ? `<div class="acciones-fila mt">
      <button class="btn btn-chico" id="eq-editar">Editar equipo</button>
      ${real ? '<button class="btn btn-chico" id="eq-probar">Probar conexión</button><button class="btn btn-chico" id="eq-sincronizar">Leer puertos del equipo</button>' : ""}
      ${puede("supervisor") ? '<button class="btn btn-chico btn-peligro" id="eq-borrar">Eliminar</button>' : ""}</div>` : ""}

    <div class="seccion-titulo">Puertos físicos ${fisicos.length ? `· ${fisicos.filter((p) => p.estado === "up").length}/${fisicos.length} arriba` : ""}</div>
    ${fisicos.length ? `<div class="frente" id="frente">
      ${fisicos.map((p) => `<button class="puerto p-${esc(p.estado)} t-${esc(p.tipo)}" data-puerto="${p.id}"
        title="${esc(p.nombre)} · ${esc(ESTADOS_PUERTO[p.estado])}${p.conectado_a ? " · → " + esc(p.conectado_a) : ""}">
        <span class="puerto-boca"></span><span class="puerto-num">${esc(numeroPuerto(p.nombre))}</span></button>`).join("")}
    </div>
    <div class="leyenda-puertos"><span><i class="p-up"></i>Arriba</span><span><i class="p-down"></i>Abajo</span><span><i class="p-admin_down"></i>Apagado</span><span><i class="p-desconocido"></i>Desconocido</span><span><i class="t-fibra-l"></i>Fibra</span></div>`
      : `<p class="kpi-pie">Sin puertos físicos registrados. ${real ? "Usa «Leer puertos del equipo» o agrégalos a mano." : "Agrégalos a mano."}</p>`}
    ${especiales.length ? `<div class="seccion-titulo">Consola, gestión y virtuales</div>
      <div class="chips">${especiales.map((p) => `<button class="chip puerto-chip p-${esc(p.estado)}" data-puerto="${p.id}">${esc(p.nombre)} · ${esc(TIPOS_PUERTO[p.tipo])}</button>`).join("")}</div>` : ""}
    <div class="tabla-envoltura mt"><table>
      <thead><tr><th>Puerto</th><th>Tipo</th><th>Estado</th><th>IP</th><th>VLAN</th><th>Conectado a</th><th>Origen</th></tr></thead>
      <tbody>${d.interfaces.map((p) => `<tr class="clic" data-puerto="${p.id}"><td class="mono nw">${esc(p.nombre)}</td><td>${esc(TIPOS_PUERTO[p.tipo])}</td>
        <td><span class="punto-estado p-${esc(p.estado)}"></span>${esc(ESTADOS_PUERTO[p.estado])}</td><td class="mono">${esc(p.ip || "—")}</td>
        <td>${esc(p.vlan || "—")}</td><td>${esc(p.conectado_a || "—")}</td><td class="kpi-pie">${esc(p.origen)} · ${fecha(p.actualizado_en)}</td></tr>`).join("")}</tbody>
    </table></div>
    ${escribe ? '<button class="btn btn-chico mt" id="eq-nuevo-puerto">+ Agregar puerto</button>' : ""}

    <div class="seccion-titulo">Últimos eventos</div>
    <ul class="lista">${d.eventos_recientes.map((e) => `<li>${chipSev(e.severidad)}<div><div class="sub msg">${esc(e.mensaje)}</div></div>
      <div class="der">${fecha(e.recibido_en)}</div></li>`).join("") || '<li class="vacio">Sin eventos.</li>'}</ul>`);

  cuerpo.querySelector("#eq-editar")?.addEventListener("click", () => { cerrarPanel(); formularioEquipo(d); });
  cuerpo.querySelector("#eq-borrar")?.addEventListener("click", async () => {
    if (!confirm(`¿Eliminar ${d.nombre}? Sus eventos se conservan sin equipo asociado.`)) return;
    try { await api(`/dispositivos/${d.id}`, { metodo: "DELETE" }); cerrarPanel(); aviso("Equipo eliminado"); cargarInventario(); }
    catch (err) { aviso(err.message, "error"); }
  });
  cuerpo.querySelector("#eq-probar")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const r = await api(`/dispositivos/${d.id}/probar`, { metodo: "POST", datos: {} });
      aviso(r.ok ? `Conexión OK (${r.comando})` : r.detalle, r.ok ? "" : "error");
    } catch (err) { aviso(err.message, "error"); }
    e.target.disabled = false;
  });
  cuerpo.querySelector("#eq-sincronizar")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const r = await api(`/dispositivos/${d.id}/interfaces/sincronizar`, { metodo: "POST", datos: {} });
      aviso(`«${r.comando}»: ${r.leidos} puertos (${r.nuevos} nuevos, ${r.actualizados} actualizados)`);
      verEquipo(d.id);
    } catch (err) { aviso(err.message, "error"); e.target.disabled = false; }
  });
  cuerpo.querySelector("#eq-nuevo-puerto")?.addEventListener("click", () => formularioPuerto(d.id));
  cuerpo.addEventListener("click", (e) => {
    const p = e.target.closest("[data-puerto]");
    if (p && escribe) formularioPuerto(d.id, d.interfaces.find((x) => x.id === Number(p.dataset.puerto)));
  });
}

function numeroPuerto(nombre) {
  const m = nombre.match(/(\d+)$/);
  return m ? m[1] : nombre.slice(0, 4);
}

function formularioPuerto(dispositivoId, p = {}) {
  const sel = (nombre, opciones, actual) => `<select name="${nombre}">${Object.entries(opciones).map(([v, t]) =>
    `<option value="${v}" ${v === actual ? "selected" : ""}>${t}</option>`).join("")}</select>`;
  const modal = abrirModal({
    titulo: p.id ? `Puerto ${p.nombre}` : "Agregar puerto",
    cuerpo: `<div class="form">
      <div class="campo"><label>Nombre</label><input name="nombre" required value="${esc(p.nombre || "")}" placeholder="GigabitEthernet0/1"></div>
      <div class="campo"><label>Tipo</label>${sel("tipo", TIPOS_PUERTO, p.tipo || "cobre")}</div>
      <div class="campo"><label>Estado</label>${sel("estado", ESTADOS_PUERTO, p.estado || "desconocido")}</div>
      <div class="campo"><label>Velocidad</label><input name="velocidad" value="${esc(p.velocidad || "")}" placeholder="1G"></div>
      <div class="campo"><label>IP / máscara</label><input name="ip" value="${esc(p.ip || "")}" placeholder="192.168.10.1/24"></div>
      <div class="campo"><label>VLAN</label><input name="vlan" value="${esc(p.vlan || "")}"></div>
      <div class="campo completo"><label>Conectado a (equipo y puerto del otro extremo)</label><input name="conectado_a" value="${esc(p.conectado_a || "")}" placeholder="LAB-FW-PERIM01 internal1"></div>
      <div class="campo completo"><label>Descripción</label><input name="descripcion" value="${esc(p.descripcion || "")}"></div>
      ${p.id ? '<p class="kpi-pie completo">El estado también se actualiza solo con los mensajes Syslog de enlace (LINK-UPDOWN, IF_STATE).</p>' : ""}
    </div>${p.id ? '<button type="button" class="btn btn-chico btn-peligro" id="borrar-puerto">Eliminar puerto</button>' : ""}`,
    alEnviar: async (datos) => {
      if (p.id) await api(`/interfaces/${p.id}`, { metodo: "PUT", datos });
      else await api(`/dispositivos/${dispositivoId}/interfaces`, { metodo: "POST", datos });
      aviso("Puerto guardado");
      verEquipo(dispositivoId);
    },
  });
  modal.querySelector("#borrar-puerto")?.addEventListener("click", async () => {
    if (!confirm(`¿Eliminar el puerto ${p.nombre}?`)) return;
    try { await api(`/interfaces/${p.id}`, { metodo: "DELETE" }); modal.remove(); verEquipo(dispositivoId); }
    catch (err) { aviso(err.message, "error"); }
  });
}

const ICONO_CONSOLA = '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4M7 9l2 2-2 2"/></svg>';
const ICONO_SSH = '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>';

document.getElementById("btn-nuevo-equipo").addEventListener("click", () => formularioEquipo());
document.getElementById("tabla-inventario").addEventListener("click", (e) => {
  const fila = e.target.closest("tr[data-id]");
  if (fila) verEquipo(Number(fila.dataset.id)).catch((err) => aviso(err.message, "error"));
});
