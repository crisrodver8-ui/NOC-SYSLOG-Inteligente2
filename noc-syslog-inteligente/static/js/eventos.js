/* eventos.js - Tabla de eventos con filtros, detalle, importación y simulador. */

const PAGINA = 50;
let desplazamiento = 0;

function filtrosActuales() {
  const p = new URLSearchParams();
  new FormData(document.getElementById("form-filtros")).forEach((v, k) => { if (v !== "") p.set(k, v); });
  return p;
}

async function cargarEventos() {
  const p = filtrosActuales();
  p.set("limite", PAGINA);
  p.set("desplazamiento", desplazamiento);
  const r = await api("/eventos?" + p.toString());
  document.getElementById("tabla-eventos").innerHTML = r.items.map((e) => `
    <tr class="clic ${e.sospechoso ? "sospechosa" : ""}" data-id="${e.id}">
      <td>${e.id}</td>
      <td class="mono nw">${fecha(e.recibido_en)}</td>
      <td>${chipSev(e.severidad)}</td>
      <td class="nw">${esc(e.dispositivo || e.hostname || e.ip_origen)}<div class="kpi-pie">${esc(e.ip_origen)}</div></td>
      <td>${e.marca ? `<span class="chip marca-chip">${esc(e.marca)}</span>` : "—"}</td>
      <td>${esc(e.facility_nombre)}</td>
      <td><div class="msg" title="${esc(e.mensaje)}">${esc(e.mensaje)}</div></td>
      <td>${e.repeticiones > 1 ? "×" + e.repeticiones : ""}</td>
      <td>${chipRiesgo(e.riesgo)}</td>
      <td>${chipsBanderas(e.banderas)}</td>
    </tr>`).join("") || `<tr><td colspan="10" class="vacio">No hay eventos con esos filtros.</td></tr>`;
  const hasta = Math.min(desplazamiento + PAGINA, r.total);
  document.getElementById("info-paginacion").textContent =
    r.total ? `Mostrando ${desplazamiento + 1}–${hasta} de ${r.total}` : "0 eventos";
  document.getElementById("pag-ant").disabled = desplazamiento === 0;
  document.getElementById("pag-sig").disabled = hasta >= r.total;
}

async function verEvento(id) {
  const e = await api(`/eventos/${id}`);
  const cuerpo = abrirPanel(`Evento #${e.id}`, `
    ${e.sospechoso ? `<div class="aviso violeta"><b>Evento sospechoso.</b> La política lo marcó por: ${esc(e.banderas.replace(/,/g, ", ").replace(/_/g, " "))}.
      El contenido se trata como dato no confiable: no se ejecuta ni se envía como instrucción a una IA.</div>` : ""}
    <dl class="dl">
      <dt>Severidad</dt><dd>${chipSev(e.severidad)}</dd>
      <dt>Facility</dt><dd>${esc(e.facility_nombre)} (${e.facility})</dd>
      <dt>Equipo</dt><dd>${esc(e.dispositivo || "No está en el inventario")}</dd>
      <dt>IP de origen</dt><dd class="mono">${esc(e.ip_origen)}</dd>
      <dt>Hostname reportado</dt><dd>${esc(e.hostname || "—")}</dd>
      <dt>Marca</dt><dd>${esc(e.marca || "—")}</dd>
      <dt>Aplicación / tag</dt><dd class="mono">${esc(e.app || "—")}</dd>
      <dt>Recibido (colector)</dt><dd>${fecha(e.recibido_en, true)} <span class="kpi-pie">· hora confiable e inmutable</span></dd>
      <dt>Fecha del equipo</dt><dd>${fecha(e.fecha_evento, true)}${e.desfase_s !== null && e.desfase_s !== undefined
        ? ` <span class="kpi-pie">· desfase ${e.desfase_s} s${Math.abs(e.desfase_s) > 300 ? " ⚠ reloj del equipo no confiable" : ""}</span>` : ""}</dd>
      <dt>Riesgo</dt><dd>${chipRiesgo(e.riesgo)} <span class="kpi-pie">de 100</span></dd>
      <dt>Repeticiones</dt><dd>${e.repeticiones} (última: ${fecha(e.ultima_vez)})</dd>
      <dt>Formato / origen</dt><dd>${esc(e.formato)} · ${esc(e.origen)}</dd>
      <dt>Política</dt><dd>${chipsBanderas(e.banderas) || "Sin observaciones"}</dd>
    </dl>
    <div class="seccion-titulo">Mensaje original (crudo)</div>
    <pre class="crudo">${esc(e.crudo)}</pre>
    <div class="acciones-fila">
      ${puede("operador", "supervisor") ? `<button class="btn btn-primario" id="ev-incidente">Crear incidente</button>` : ""}
      ${puede("operador", "supervisor") && e.dispositivo_id ? `<button class="btn" id="ev-accion">Proponer acción</button>` : ""}
    </div>`);
  cuerpo.querySelector("#ev-incidente")?.addEventListener("click", () => {
    cerrarPanel();
    nuevoIncidente({ evento_id: e.id, severidad: e.severidad,
      titulo: `${NOC.SEVERIDADES[e.severidad]} en ${e.dispositivo || e.ip_origen}`,
      descripcion: `Evento #${e.id}: ${e.mensaje.slice(0, 300)}` });
  });
  cuerpo.querySelector("#ev-accion")?.addEventListener("click", () => {
    cerrarPanel();
    nuevaAccion({ evento_id: e.id, dispositivo_id: e.dispositivo_id });
  });
}

// --- eventos de la interfaz ---
document.getElementById("form-filtros").addEventListener("submit", (e) => {
  e.preventDefault(); desplazamiento = 0; cargarEventos().catch((err) => aviso(err.message, "error"));
});
document.getElementById("form-filtros").addEventListener("reset", () => {
  setTimeout(() => { desplazamiento = 0; cargarEventos(); }, 0);
});
document.getElementById("pag-ant").addEventListener("click", () => { desplazamiento = Math.max(0, desplazamiento - PAGINA); cargarEventos(); });
document.getElementById("pag-sig").addEventListener("click", () => { desplazamiento += PAGINA; cargarEventos(); });
document.getElementById("tabla-eventos").addEventListener("click", (e) => {
  const fila = e.target.closest("tr[data-id]");
  if (fila) verEvento(fila.dataset.id).catch((err) => aviso(err.message, "error"));
});

document.getElementById("btn-simular").addEventListener("click", async () => {
  const escenario = document.getElementById("escenario-sim").value;
  try {
    const r = await api("/simulador", { metodo: "POST", datos: { escenario, cantidad: 30 } });
    const partes = Object.entries(r.resultado).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ");
    aviso(`Simulación «${escenario}»: ${r.enviados} mensajes → ${partes}`);
    desplazamiento = 0;
    cargarEventos();
  } catch (err) { aviso(err.message, "error"); }
});

document.getElementById("archivo-syslog").addEventListener("change", async (e) => {
  const archivo = e.target.files[0];
  if (!archivo) return;
  const fd = new FormData();
  fd.append("archivo", archivo);
  try {
    const r = await api("/eventos/importar", { metodo: "POST", formulario: fd });
    aviso(`Importado: ${r.lineas} líneas → ${r.almacenado} nuevos, ${r.duplicado} duplicados`);
    desplazamiento = 0;
    cargarEventos();
  } catch (err) { aviso(err.message, "error"); }
  e.target.value = "";
});
