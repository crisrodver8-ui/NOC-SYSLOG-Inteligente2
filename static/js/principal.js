/* principal.js - Navegación entre vistas, permisos por rol y refresco automático. */

const VISTAS = {
  resumen: ["Panel general", "Estado de la red en las últimas 24 horas", cargarResumen],
  eventos: ["Eventos Syslog", "Recepción UDP, importación de archivos y simulador", cargarEventos],
  incidentes: ["Incidentes", "Creación, asignación, seguimiento y cierre", cargarIncidentes],
  acciones: ["Aprobaciones", "Acciones de respuesta con revisión humana obligatoria", cargarAcciones],
  inventario: ["Inventario", "Equipos, puertos físicos, consola y lista permitida", cargarInventario],
  configuraciones: ["Configuraciones", "Plantillas Syslog comentadas para Cisco, Fortinet y Huawei", async () => {}],
  consola: ["Consola", "Gestor de solo lectura: simulado o real por SSH/consola desde el servidor", cargarConsola],
  politica: ["Política IA", "Defensa frente a acciones de agentes de inteligencia artificial", cargarPolitica],
  verificacion: ["Verificación", "Políticas Syslog verificadas, hora NTP, integridad y alertas", cargarVerificacion],
  auditoria: ["Auditoría", "Registro encadenado e inmutable: quién hizo qué y cuándo", cargarAuditoria],
  usuarios: ["Usuarios", "Cuentas, roles y claves temporales", cargarUsuarios],
  api: ["API", "Tokens de acceso e índice de la API REST", cargarApi],
};
let vistaActual = "resumen";
let intervalos = [];

function irA(vista) {
  if (!VISTAS[vista]) vista = "resumen";
  const boton = document.querySelector(`#menu button[data-vista="${vista}"]`);
  if (boton && boton.hidden) vista = "resumen";       // vista no permitida para el rol
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
  // Oculta lo que el rol no puede usar. El backend valida igual: esto es solo comodidad.
  const escribe = puede("operador");
  ["btn-nuevo-incidente", "btn-nueva-accion", "btn-nuevo-equipo", "btn-simular", "escenario-sim"].forEach((id) => {
    document.getElementById(id).hidden = !escribe;
  });
  document.querySelector('label[for="archivo-syslog"]').hidden = !escribe;
  document.querySelectorAll("[data-rol]").forEach((el) => { el.hidden = !puede(el.dataset.rol); });
}

/** Se llama cuando hay una sesión válida. */
async function arrancarApp(usuario) {
  NOC.usuario = usuario.usuario;
  NOC.rol = usuario.rol;
  document.getElementById("acceso").hidden = true;
  document.getElementById("app").hidden = false;
  document.getElementById("nombre-usuario").textContent = usuario.nombre || usuario.usuario;
  document.getElementById("rol-usuario").textContent = usuario.rol;
  aplicarRol();

  NOC.usuarios = await api("/usuarios/nombres");
  await cargarDispositivos();
  document.getElementById("filtro-equipo").innerHTML = `<option value="">Todos</option>` + opcionesEquipos();
  document.getElementById("filtro-sev").innerHTML = `<option value="">Todas</option>` +
    NOC.SEVERIDADES.map((s, i) => `<option value="${i}">${i} ${s}</option>`).join("");

  let inicial = "resumen";
  try { inicial = localStorage.getItem("noc-vista") || "resumen"; } catch { /* sin almacenamiento */ }
  irA(inicial);
  estadoReceptor();

  intervalos.forEach(clearInterval);
  intervalos = [
    setInterval(() => {
      estadoReceptor();
      if (vistaActual === "resumen" && !document.getElementById("panel")) cargarResumen().catch(() => {});
    }, 15000),
    setInterval(() => {
      document.getElementById("reloj").textContent = new Date().toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "medium" });
    }, 1000),
  ];
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

// --- navegación ---
document.getElementById("menu").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-vista]");
  if (b) irA(b.dataset.vista);
});
document.body.addEventListener("click", (e) => {
  const b = e.target.closest("[data-ir]");
  if (b) irA(b.dataset.ir);
});

iniciarAcceso();
