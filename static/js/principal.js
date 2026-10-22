/* principal.js - Navegación entre vistas, selección de usuario y refresco automático. */

const VISTAS = {
  resumen: ["Panel general", "Estado de la red en las últimas 24 horas", cargarResumen],
  eventos: ["Eventos Syslog", "Recepción UDP, importación de archivos y simulador", cargarEventos],
  incidentes: ["Incidentes", "Creación, asignación, seguimiento y cierre", cargarIncidentes],
  acciones: ["Aprobaciones", "Acciones de respuesta con revisión humana obligatoria", cargarAcciones],
  inventario: ["Inventario", "Equipos de red y lista permitida de fuentes Syslog", cargarInventario],
  configuraciones: ["Configuraciones", "Plantillas Syslog comentadas para Cisco, Fortinet y Huawei", async () => {}],
  consola: ["Consola", "Terminal simulada de solo lectura con comandos permitidos y bloqueados", cargarConsola],
  politica: ["Política IA", "Defensa frente a acciones de agentes de inteligencia artificial", cargarPolitica],
  auditoria: ["Auditoría", "Quién hizo qué, cuándo y con qué resultado", cargarAuditoria],
};
let vistaActual = "resumen";

function irA(vista) {
  vistaActual = vista;
  document.querySelectorAll("#menu button").forEach((b) => b.classList.toggle("activo", b.dataset.vista === vista));
  document.querySelectorAll(".vista").forEach((s) => s.classList.toggle("activa", s.id === "vista-" + vista));
  const [titulo, subtitulo, cargar] = VISTAS[vista];
  document.getElementById("titulo-vista").textContent = titulo;
  document.getElementById("subtitulo-vista").textContent = subtitulo;
  try { localStorage.setItem("noc-vista", vista); } catch { /* sin almacenamiento */ }
  cargar().catch((err) => aviso(err.message, "error"));
}

function aplicarRol() {
  // Oculta los botones que el rol actual no puede usar (el backend también lo valida)
  const escribe = puede("operador", "supervisor");
  ["btn-nuevo-incidente", "btn-nueva-accion", "btn-nuevo-equipo", "btn-simular"].forEach((id) => {
    document.getElementById(id).hidden = !escribe;
  });
  document.getElementById("escenario-sim").hidden = !escribe;
  document.querySelector('label[for="archivo-syslog"]').hidden = !escribe;
}

async function iniciar() {
  NOC.usuarios = await api("/usuarios");
  let guardado = null;
  try { guardado = localStorage.getItem("noc-usuario"); } catch { /* sin almacenamiento */ }
  NOC.usuario = NOC.usuarios[guardado] ? guardado : Object.keys(NOC.usuarios)[0]; // por defecto: operador1
  NOC.rol = NOC.usuarios[NOC.usuario];

  const selector = document.getElementById("selector-usuario");
  selector.innerHTML = Object.keys(NOC.usuarios).map((u) => `<option ${u === NOC.usuario ? "selected" : ""}>${esc(u)}</option>`).join("");
  document.getElementById("rol-usuario").textContent = NOC.rol;
  selector.addEventListener("change", () => {
    NOC.usuario = selector.value;
    NOC.rol = NOC.usuarios[NOC.usuario];
    document.getElementById("rol-usuario").textContent = NOC.rol;
    try { localStorage.setItem("noc-usuario", NOC.usuario); } catch { /* sin almacenamiento */ }
    aplicarRol();
    irA(vistaActual);
    aviso(`Ahora trabajas como ${NOC.usuario} (${NOC.rol})`);
  });
  aplicarRol();

  // Filtros de eventos
  await cargarDispositivos();
  document.getElementById("filtro-equipo").innerHTML = `<option value="">Todos</option>` + opcionesEquipos();
  document.getElementById("filtro-sev").innerHTML = `<option value="">Todas</option>` +
    NOC.SEVERIDADES.map((s, i) => `<option value="${i}">${i} ${s}</option>`).join("");

  document.getElementById("menu").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-vista]");
    if (b) irA(b.dataset.vista);
  });
  document.body.addEventListener("click", (e) => {
    const b = e.target.closest("[data-ir]");
    if (b) irA(b.dataset.ir);
  });

  let inicial = "resumen";
  try { inicial = localStorage.getItem("noc-vista") || "resumen"; } catch { /* sin almacenamiento */ }
  irA(VISTAS[inicial] ? inicial : "resumen");
  estadoReceptor();

  // Refresco automático del panel cada 15 s
  setInterval(() => {
    estadoReceptor();
    if (vistaActual === "resumen" && !document.getElementById("panel")) cargarResumen().catch(() => {});
  }, 15000);
  setInterval(() => {
    document.getElementById("reloj").textContent = new Date().toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "medium" });
  }, 1000);
}

async function estadoReceptor() {
  const punto = document.getElementById("receptor-punto");
  const texto = document.getElementById("receptor-texto");
  try {
    const r = await fetch("/api/estado").then((x) => x.json());
    const rec = r.receptor;
    punto.className = "punto " + (rec.activo ? "ok" : "mal");
    texto.textContent = rec.activo ? `Receptor UDP :${rec.puerto} activo` : "Receptor UDP apagado";
    texto.title = rec.error || "";
  } catch {
    punto.className = "punto mal"; texto.textContent = "Servidor sin respuesta";
  }
}

iniciar().catch((err) => aviso(err.message, "error"));
