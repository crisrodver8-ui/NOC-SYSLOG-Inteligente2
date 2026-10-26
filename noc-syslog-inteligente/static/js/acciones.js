/* acciones.js - Propuesta, revisión humana, aprobación, ejecución y verificación. */

const PASOS = ["Evento", "Validación", "Propuesta", "Revisión humana", "Aprobación", "Ejecución", "Verificación", "Auditoría"];
// Cuántos pasos están cumplidos según el estado de la acción
const AVANCE = { propuesta: 3, aprobada: 5, rechazada: 4, ejecutada: 6, verificada: 8 };
let catalogo = null;

function flujo(estado) {
  const n = AVANCE[estado];
  return `<div class="flujo">${PASOS.map((p, i) => {
    const clase = estado === "rechazada" && i === 4 ? "fallo" : i < n ? "hecho" : "";
    return `<span class="paso ${clase}">${p}</span>`;
  }).join("")}</div>`;
}

async function cargarAcciones() {
  catalogo = catalogo || await api("/acciones/catalogo");
  const lista = await api("/acciones");
  document.getElementById("lista-acciones").innerHTML = lista.map((a) => {
    const botones = [];
    if (a.estado === "propuesta" && puede("supervisor") && a.propuesta_por !== NOC.usuario) {
      botones.push(`<button class="btn btn-primario btn-chico" data-op="aprobar" data-id="${a.id}">Aprobar</button>`,
                   `<button class="btn btn-peligro btn-chico" data-op="rechazar" data-id="${a.id}">Rechazar</button>`);
    }
    if (a.estado === "aprobada" && puede("operador", "supervisor")) {
      botones.push(`<button class="btn btn-primario btn-chico" data-op="ejecutar" data-id="${a.id}">Ejecutar (simulado)</button>`);
    }
    if (a.estado === "ejecutada" && puede("operador", "supervisor")) {
      botones.push(`<button class="btn btn-primario btn-chico" data-op="verificar" data-id="${a.id}">Verificar</button>`);
    }
    const espera = a.estado === "propuesta" && a.propuesta_por === NOC.usuario
      ? `<span class="kpi-pie">Esperando revisión de otro supervisor (no puedes aprobar tu propia propuesta).</span>` : "";
    return `<div class="accion-tarjeta">
      <div class="accion-cab">${chipEstado(a.estado, a.estado)}
        <span class="titulo">#${a.id} ${esc(catalogo[a.tipo]?.nombre || a.tipo)}${a.parametro ? ": " + esc(a.parametro) : ""}</span>
        <span class="chip marca-chip">${esc(a.dispositivo)} · ${esc(a.marca)}</span>
        ${a.incidente_id ? `<span class="chip marca-chip">incidente #${a.incidente_id}</span>` : ""}</div>
      ${flujo(a.estado)}
      <div class="sub">Justificación: ${esc(a.justificacion)}</div>
      <pre class="comando">${esc(a.comando)}</pre>
      <div class="kpi-pie">Propuesta por ${esc(a.propuesta_por)} · ${fecha(a.creado_en)}
        ${a.revisada_por ? ` · revisada por ${esc(a.revisada_por)}${a.comentario_revision ? ` («${esc(a.comentario_revision)}»)` : ""}` : ""}
        ${a.ejecutada_por ? ` · ejecutada por ${esc(a.ejecutada_por)}` : ""}
        ${a.verificada_por ? ` · verificada por ${esc(a.verificada_por)}: ${esc(a.verificacion)}` : ""}</div>
      <div class="acciones-fila mt">${botones.join("")}${espera}</div>
    </div>`;
  }).join("") || `<p class="vacio">No hay acciones. Abre un evento o incidente y pulsa «Proponer acción».</p>`;
}

async function nuevaAccion(previo = {}) {
  catalogo = catalogo || await api("/acciones/catalogo");
  const modal = abrirModal({
    titulo: "Proponer acción de respuesta",
    boton: "Enviar a revisión",
    cuerpo: `<div class="aviso info">La acción se elige de un catálogo cerrado. El comando se genera desde una plantilla y nunca se copia del texto de un log.</div>
    <div class="form">
      <div class="campo completo"><label>Equipo (solo lista permitida)</label><select name="dispositivo_id" required>${opcionesEquipos(previo.dispositivo_id, true)}</select></div>
      <div class="campo"><label>Acción</label><select name="tipo" id="accion-tipo">${Object.entries(catalogo).map(([k, v]) =>
        `<option value="${k}">${esc(v.nombre)}</option>`).join("")}</select></div>
      <div class="campo"><label id="accion-param-etq">Parámetro</label><input name="parametro" id="accion-param"></div>
      <div class="campo completo"><label>Justificación</label><textarea name="justificacion" required minlength="10"></textarea></div>
      <input type="hidden" name="evento_id" value="${esc(previo.evento_id || "")}">
      <input type="hidden" name="incidente_id" value="${esc(previo.incidente_id || "")}">
    </div>`,
    alEnviar: async (d) => {
      await api("/acciones", { metodo: "POST", datos: {
        ...d, dispositivo_id: Number(d.dispositivo_id),
        evento_id: d.evento_id ? Number(d.evento_id) : null,
        incidente_id: d.incidente_id ? Number(d.incidente_id) : null } });
      aviso("Acción propuesta. Un supervisor distinto debe revisarla.");
      irA("acciones");
    },
  });
  const tipo = modal.querySelector("#accion-tipo");
  const ajustar = () => {
    const p = catalogo[tipo.value].parametro;
    const campo = modal.querySelector("#accion-param");
    campo.disabled = !p;
    campo.placeholder = p === "ip" ? "ej. 203.0.113.66" : p === "usuario" ? "ej. svc-ai-agent" : "no requiere";
    modal.querySelector("#accion-param-etq").textContent = p === "ip" ? "IP a bloquear" : p === "usuario" ? "Usuario" : "Parámetro";
  };
  tipo.addEventListener("change", ajustar);
  ajustar();
}

document.getElementById("btn-nueva-accion").addEventListener("click", () => nuevaAccion());
document.getElementById("lista-acciones").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-op]");
  if (!b) return;
  const id = b.dataset.id;
  const op = b.dataset.op;
  if (op === "aprobar" || op === "rechazar") {
    abrirModal({
      titulo: op === "aprobar" ? `Aprobar acción #${id}` : `Rechazar acción #${id}`,
      boton: op === "aprobar" ? "Aprobar" : "Rechazar",
      cuerpo: `<div class="campo"><label>Comentario de la revisión ${op === "rechazar" ? "(obligatorio)" : "(opcional)"}</label><textarea name="comentario"></textarea></div>`,
      alEnviar: async (d) => {
        await api(`/acciones/${id}/revisar`, { metodo: "POST", datos: { decision: op, comentario: d.comentario } });
        aviso(op === "aprobar" ? "Acción aprobada" : "Acción rechazada"); cargarAcciones();
      },
    });
  } else if (op === "ejecutar") {
    try {
      await api(`/acciones/${id}/ejecutar`, { metodo: "POST", datos: {} });
      aviso("Ejecución simulada registrada"); cargarAcciones();
    } catch (err) { aviso(err.message, "error"); }
  } else if (op === "verificar") {
    abrirModal({
      titulo: `Verificar acción #${id}`,
      boton: "Registrar verificación",
      cuerpo: `<div class="form"><div class="campo completo"><label>¿Cómo se verificó?</label><textarea name="verificacion" required></textarea></div>
        <label class="casilla completo"><input type="checkbox" name="exito" checked> La acción tuvo el efecto esperado</label></div>`,
      alEnviar: async (d) => {
        await api(`/acciones/${id}/verificar`, { metodo: "POST", datos: d });
        aviso("Verificación registrada en la auditoría"); cargarAcciones();
      },
    });
  }
});
