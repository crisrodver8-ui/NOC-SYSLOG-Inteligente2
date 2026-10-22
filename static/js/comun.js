/* =====================================================================
   comun.js - utilidades compartidas por todas las vistas.

   SEGURIDAD: todo texto que viene del servidor (en especial los mensajes
   Syslog, que son datos NO confiables) se pasa por esc() antes de
   insertarlo en el HTML. Así un log con "<script>" se muestra como texto
   y nunca se ejecuta.
   ===================================================================== */
const NOC = {
  usuario: null,
  rol: null,
  usuarios: {},
  dispositivos: [],
  SEVERIDADES: ["Emergency", "Alert", "Critical", "Error", "Warning", "Notice", "Informational", "Debug"],
  ESTADOS_INC: { abierto: "Abierto", en_progreso: "En progreso", resuelto: "Resuelto", cerrado: "Cerrado" },
};

/** Escapa caracteres especiales de HTML. */
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Llamada a la API. Envía el usuario actual en la cabecera X-Usuario. */
async function api(ruta, { metodo = "GET", datos, formulario } = {}) {
  const opciones = { method: metodo, headers: { "X-Usuario": NOC.usuario || "" } };
  if (formulario) {
    opciones.body = formulario;
  } else if (datos !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(datos);
  }
  const resp = await fetch("/api" + ruta, opciones);
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(json.error || `Error ${resp.status}`);
  return json;
}

/** "2026-10-09T14:03:22" -> "09/10 14:03:22" */
function fecha(iso, conAnio = false) {
  if (!iso) return "—";
  const [f, h = ""] = iso.split("T");
  const [a, m, d] = f.split("-");
  return `${d}/${m}${conAnio ? "/" + a : ""} ${h.slice(0, 8)}`;
}

function chipSev(n) {
  return `<span class="sev s${Number(n)}">${Number(n)} ${esc(NOC.SEVERIDADES[n] || "")}</span>`;
}

function chipEstado(estado, texto) {
  return `<span class="chip estado-${esc(estado)}">${esc(texto || NOC.ESTADOS_INC[estado] || estado)}</span>`;
}

const BANDERAS_INFO = new Set(["acceso", "cambio_config", "fallo_autenticacion"]);
function chipsBanderas(cadena) {
  if (!cadena) return "";
  return `<span class="chips">${cadena.split(",").map((b) =>
    `<span class="chip bandera ${BANDERAS_INFO.has(b) ? "info" : ""}">${esc(b.replace(/_/g, " "))}</span>`).join("")}</span>`;
}

function aviso(texto, tipo = "") {
  const t = document.createElement("div");
  t.className = "toast " + tipo;
  t.textContent = texto;
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), 4500);
}

function puede(...roles) { return roles.includes(NOC.rol); }

function opcionesUsuarios(seleccionado = "") {
  return `<option value="">— Sin asignar —</option>` + Object.entries(NOC.usuarios)
    .filter(([, rol]) => rol !== "auditor")
    .map(([u, rol]) => `<option value="${esc(u)}" ${u === seleccionado ? "selected" : ""}>${esc(u)} (${esc(rol)})</option>`).join("");
}

function opcionesEquipos(seleccionado = "", soloAutorizados = false) {
  return NOC.dispositivos.filter((d) => !soloAutorizados || d.autorizado)
    .map((d) => `<option value="${d.id}" ${String(d.id) === String(seleccionado) ? "selected" : ""}>${esc(d.nombre)} · ${esc(d.ip)}</option>`).join("");
}

async function cargarDispositivos() {
  NOC.dispositivos = await api("/dispositivos");
  return NOC.dispositivos;
}

/* ---------------------------------------------------------- modal */
/**
 * Abre un formulario modal.
 *  titulo, cuerpo (HTML con campos name="..."), boton, alEnviar(datos) -> Promise
 */
function abrirModal({ titulo, cuerpo, boton = "Guardar", alEnviar }) {
  const capa = document.createElement("div");
  capa.className = "modal";
  capa.innerHTML = `
    <form class="modal-caja">
      <div class="modal-cab"><h3>${esc(titulo)}</h3><button type="button" class="cerrar" aria-label="Cerrar">×</button></div>
      <div class="modal-cuerpo">${cuerpo}<p class="error-form" hidden></p></div>
      <div class="modal-pie"><button type="button" class="btn cancelar">Cancelar</button><button class="btn btn-primario" type="submit">${esc(boton)}</button></div>
    </form>`;
  const cerrar = () => capa.remove();
  capa.querySelector(".cerrar").addEventListener("click", cerrar);
  capa.querySelector(".cancelar").addEventListener("click", cerrar);
  capa.addEventListener("click", (e) => { if (e.target === capa) cerrar(); });
  const form = capa.querySelector("form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const datos = {};
    new FormData(form).forEach((v, k) => { datos[k] = v; });
    form.querySelectorAll("input[type=checkbox]").forEach((c) => { datos[c.name] = c.checked; });
    const error = form.querySelector(".error-form");
    try {
      await alEnviar(datos);
      cerrar();
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
    }
  });
  document.body.appendChild(capa);
  form.querySelector("input, select, textarea")?.focus();
  return capa;
}

/* ---------------------------------------------------------- panel lateral */
function abrirPanel(titulo, html) {
  cerrarPanel();
  const cortina = document.createElement("div");
  cortina.className = "cortina";
  cortina.id = "cortina";
  const panel = document.createElement("aside");
  panel.className = "panel";
  panel.id = "panel";
  panel.innerHTML = `<div class="panel-cab"><h3>${esc(titulo)}</h3><button class="cerrar" aria-label="Cerrar">×</button></div>
                     <div class="panel-cuerpo">${html}</div>`;
  cortina.addEventListener("click", cerrarPanel);
  panel.querySelector(".cerrar").addEventListener("click", cerrarPanel);
  document.body.append(cortina, panel);
  return panel.querySelector(".panel-cuerpo");
}

function cerrarPanel() {
  document.getElementById("panel")?.remove();
  document.getElementById("cortina")?.remove();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { cerrarPanel(); document.querySelector(".modal")?.remove(); }
});
