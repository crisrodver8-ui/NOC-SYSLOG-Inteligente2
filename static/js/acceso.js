/* acceso.js - Configuración inicial (primer admin), inicio de sesión, cambio de clave y salida. */

let modoAcceso = "login";   // login | inicial | cambio

function configurarAcceso(modo, texto = "") {
  modoAcceso = modo;
  const $ = (id) => document.getElementById(id);
  $("acceso").hidden = false;
  $("app").hidden = true;
  $("acceso-error").hidden = true;
  $("form-acceso").reset();
  const titulos = {
    login: ["Iniciar sesión", "Ingresa con tu usuario y clave.", "Entrar"],
    inicial: ["Configuración inicial", "No hay usuarios todavía. Crea la cuenta del administrador.", "Crear administrador"],
    cambio: ["Cambia tu clave", "Tu clave es temporal. Define una clave personal para continuar.", "Guardar clave"],
  }[modo];
  $("acceso-titulo").textContent = titulos[0];
  $("acceso-texto").textContent = texto || titulos[1];
  $("acceso-boton").textContent = titulos[2];
  $("campo-usuario").hidden = modo === "cambio";
  $("acc-usuario").required = modo !== "cambio";
  $("campo-nombre").hidden = modo !== "inicial";
  $("campo-actual").hidden = modo !== "cambio";
  $("acc-actual").required = modo === "cambio";
  $("campo-repetir").hidden = modo === "login";
  $("acc-repetir").required = modo !== "login";
  $("acceso-ayuda").hidden = modo === "login";
  $("etq-clave").textContent = modo === "login" ? "Clave" : "Nueva clave";
  $("acc-clave").autocomplete = modo === "login" ? "current-password" : "new-password";
  (modo === "cambio" ? $("acc-actual") : $("acc-usuario")).focus();
}

/** La pide api() cuando la sesión vence (401). */
function mostrarAcceso() {
  if (document.getElementById("acceso").hidden) configurarAcceso("login", "Tu sesión terminó. Vuelve a ingresar.");
}

async function iniciarAcceso() {
  try {
    const s = await api("/sesion");
    if (s.configuracion_inicial) return configurarAcceso("inicial");
    if (!s.autenticado) return configurarAcceso("login");
    if (s.usuario.debe_cambiar_clave) return configurarAcceso("cambio");
    await arrancarApp(s.usuario);
  } catch (err) {
    configurarAcceso("login", "No se pudo contactar el servidor: " + err.message);
  }
}

document.getElementById("form-acceso").addEventListener("submit", async (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.target));
  const error = document.getElementById("acceso-error");
  error.hidden = true;
  try {
    if (modoAcceso !== "login" && d.clave !== d.repetir) throw new Error("Las claves no coinciden.");
    let r;
    if (modoAcceso === "inicial") {
      r = await api("/sesion/inicial", { metodo: "POST", datos: { usuario: d.usuario, nombre: d.nombre, clave: d.clave } });
    } else if (modoAcceso === "login") {
      r = await api("/sesion/login", { metodo: "POST", datos: { usuario: d.usuario, clave: d.clave } });
      if (r.usuario.debe_cambiar_clave) return configurarAcceso("cambio");
    } else {
      await api("/sesion/clave", { metodo: "POST", datos: { actual: d.actual, nueva: d.clave } });
      aviso("Clave actualizada");
      r = await api("/sesion");
    }
    await arrancarApp(r.usuario);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  }
});

document.getElementById("btn-salir").addEventListener("click", async () => {
  await api("/sesion/logout", { metodo: "POST", datos: {} }).catch(() => {});
  intervalos.forEach(clearInterval);
  configurarAcceso("login", "Sesión cerrada.");
});

document.getElementById("btn-mi-clave").addEventListener("click", () => {
  abrirModal({
    titulo: "Cambiar mi clave",
    boton: "Guardar",
    cuerpo: `<div class="form">
      <div class="campo completo"><label>Clave actual</label><input type="password" name="actual" required autocomplete="current-password"></div>
      <div class="campo"><label>Nueva clave</label><input type="password" name="nueva" required autocomplete="new-password"></div>
      <div class="campo"><label>Repite la nueva clave</label><input type="password" name="repetir" required autocomplete="new-password"></div>
      <p class="kpi-pie completo">Mínimo 10 caracteres, con letras y números. Al cambiarla se cierran tus otras sesiones.</p></div>`,
    alEnviar: async (d) => {
      if (d.nueva !== d.repetir) throw new Error("Las claves no coinciden.");
      await api("/sesion/clave", { metodo: "POST", datos: { actual: d.actual, nueva: d.nueva } });
      aviso("Clave actualizada");
    },
  });
});
