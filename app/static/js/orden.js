// Lógica del formulario de Orden de Servicio: PIN numérico, patrón y cálculo financiero en vivo.
document.addEventListener("DOMContentLoaded", function () {
  inicializarPin();
  inicializarPatron();
  inicializarCalculo();
  inicializarMarcaModelo();
  inicializarServicioRapido();
  inicializarValidacionEnvio();
});

// Antes de enviar el formulario, verifica que los campos obligatorios de
// marca, modelo y condición física estén completos. Si falta algo, se
// bloquea el envío (sin perder nada de lo ya llenado) y se muestra un
// aviso claro en vez de dejar que se cree una orden incompleta.
//
// EXCEPCIÓN: si en "Servicios adicionales" (abajo) ya se agregó un servicio
// sin costo (precio en 0 o vacío), no se exige la Marca del equipo — el
// cliente ya queda identificado con su nombre y teléfono (Cliente *).
function tieneServicioSinCostoAbajo() {
  var filas = document.querySelectorAll("#serviciosFilas .servicio-fila");
  for (var i = 0; i < filas.length; i++) {
    var nombre = filas[i].querySelector('input[name="servicio_nombre"]');
    var precio = filas[i].querySelector('input[name="servicio_precio"]');
    if (nombre && nombre.value.trim()) {
      var monto = precio ? parseFloat(precio.value) : 0;
      if (!monto || monto <= 0) return true;
    }
  }
  return false;
}

function inicializarValidacionEnvio() {
  var form = document.querySelector(".content form");
  var errorBox = document.getElementById("ordenFormError");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    var hiddenMarca = document.getElementById("hiddenMarca");
    var hiddenModelo = document.getElementById("hiddenModelo");
    var condicionGrid = document.getElementById("condicionGrid");
    var sinCosto = tieneServicioSinCostoAbajo();

    var faltantes = [];
    if (!sinCosto && (!hiddenMarca || !hiddenMarca.value.trim())) faltantes.push("la marca del equipo");
    if (!hiddenModelo || !hiddenModelo.value.trim()) faltantes.push("el modelo del equipo");
    if (condicionGrid && !condicionGrid.querySelector('input[type=checkbox]:checked')) {
      faltantes.push('la condición física al recibir (marca al menos una opción, o "Sin daños visibles" si está en buen estado)');
    }

    if (faltantes.length > 0) {
      e.preventDefault();
      if (errorBox) {
        errorBox.textContent = "Antes de guardar, completa lo siguiente: " + faltantes.join("; ") + ".";
        errorBox.style.display = "block";
        errorBox.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return false;
    }
    if (errorBox) errorBox.style.display = "none";
  });
}

// ---------------------------------------------------------------------------
// Acceso al equipo: métodos de bloqueo, PIN, patrón y contraseña.
// ---------------------------------------------------------------------------
function inicializarPin() {
  var card = document.querySelector(".acc-card");
  if (!card) return;
  var checks = card.querySelectorAll('input[name="tipo_bloqueo"]');
  var resumen = document.getElementById("accResumen");

  function marcados() {
    return Array.prototype.filter.call(checks, function (c) { return c.checked; }).map(function (c) { return c.value; });
  }
  function actualizarPaneles() {
    var m = marcados();
    card.querySelectorAll(".acc-panel").forEach(function (p) {
      var claves = (p.getAttribute("data-metodo") || "").split(" ");
      p.hidden = !claves.some(function (k) { return m.indexOf(k) >= 0; });
    });
    checks.forEach(function (c) { c.closest(".acc-metodo").classList.toggle("on", c.checked); });
    if (resumen) {
      var nombres = Array.prototype.filter.call(checks, function (c) { return c.checked; })
        .map(function (c) { return c.closest(".acc-metodo").querySelector("span").textContent; });
      resumen.textContent = nombres.length ? nombres.join(" · ") : (card.open ? "toca para ocultar" : "toca para registrar el bloqueo");
    }
  }
  checks.forEach(function (c) {
    c.addEventListener("change", function () {
      var exclusivo = c.value === "sin" || c.value === "no_dio";
      if (c.checked) {
        checks.forEach(function (o) {
          if (o === c) return;
          var oExcl = o.value === "sin" || o.value === "no_dio";
          if (exclusivo || oExcl) o.checked = false;
        });
      }
      actualizarPaneles();
      if (c.checked) {
        var panel = card.querySelector('.acc-panel[data-metodo~="' + c.value + '"]');
        var foco = panel && panel.querySelector("input:not([type=hidden])");
        if (foco && window.matchMedia("(pointer:fine)").matches) foco.focus();
      }
    });
  });
  card.addEventListener("toggle", actualizarPaneles);

  // Botón "Ver" de los campos de clave.
  card.querySelectorAll(".acc-ojo").forEach(function (b) {
    b.addEventListener("click", function () {
      var inp = document.getElementById(b.getAttribute("data-ver"));
      if (!inp) return;
      var ver = inp.type === "password";
      inp.type = ver ? "text" : "password";
      b.textContent = ver ? "Ocultar" : "Ver";
    });
  });

  // Teclado del PIN (también se puede escribir con el teclado).
  var pin = document.getElementById("pinValor");
  var pad = document.getElementById("pinPad");
  if (pin) {
    pin.addEventListener("input", function () { pin.value = pin.value.replace(/\D/g, "").slice(0, 20); });
  }
  if (pad && pin) {
    pad.querySelectorAll("button[data-num]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (pin.value.length >= 20) return;
        pin.value += btn.getAttribute("data-num");
        btn.classList.add("pulsado");
        setTimeout(function () { btn.classList.remove("pulsado"); }, 120);
      });
    });
    var borrar = document.getElementById("pinBorrar");
    var limpiar = document.getElementById("pinLimpiar");
    if (borrar) borrar.addEventListener("click", function () { pin.value = pin.value.slice(0, -1); });
    if (limpiar) limpiar.addEventListener("click", function () { pin.value = ""; });
  }
  var sim = document.getElementById("pinSim");
  if (sim) sim.addEventListener("input", function () { sim.value = sim.value.replace(/\D/g, "").slice(0, 20); });

  actualizarPaneles();
}

function inicializarPatron() {
  var grid = document.getElementById("patronGrid");
  var hidden = document.getElementById("patronValor");
  var display = document.getElementById("patronDisplay");
  var linea = document.getElementById("patronLinea");
  if (!grid || !hidden) return;

  var seleccion = (hidden.value || "").split(",").filter(function (x) { return /^[1-9]$/.test(x); });
  var dibujando = false;
  var puntoMovil = null; // punto donde está el dedo mientras se arrastra

  function centro(id) {
    var n = parseInt(id, 10) - 1;
    return { x: 50 + (n % 3) * 100, y: 50 + Math.floor(n / 3) * 100 };
  }
  function pintar() {
    grid.querySelectorAll(".acc-punto").forEach(function (p) {
      var idx = seleccion.indexOf(p.getAttribute("data-id"));
      p.classList.toggle("on", idx >= 0);
      p.classList.toggle("inicio", idx === 0);
      p.querySelector("span").textContent = idx >= 0 ? String(idx + 1) : "";
    });
    var pts = seleccion.map(function (id) { var c = centro(id); return c.x + "," + c.y; });
    if (puntoMovil && seleccion.length) pts.push(puntoMovil.x + "," + puntoMovil.y);
    if (linea) linea.setAttribute("points", pts.join(" "));
    if (display) display.textContent = seleccion.length ? seleccion.join(" → ") : "sin dibujar";
    hidden.value = seleccion.join(",");
  }
  function agregar(id) {
    if (seleccion.indexOf(id) >= 0) return;
    // Como en Android: si se salta un punto que está en medio, también cuenta.
    var ultimo = seleccion[seleccion.length - 1];
    if (ultimo) {
      var a = parseInt(ultimo, 10) - 1, b = parseInt(id, 10) - 1;
      var fa = Math.floor(a / 3), ca = a % 3, fb = Math.floor(b / 3), cb = b % 3;
      if ((fa + fb) % 2 === 0 && (ca + cb) % 2 === 0) {
        var medio = String(((fa + fb) / 2) * 3 + (ca + cb) / 2 + 1);
        if (seleccion.indexOf(medio) < 0) seleccion.push(medio);
      }
    }
    seleccion.push(id);
    if (navigator.vibrate) { try { navigator.vibrate(8); } catch (e) {} }
  }
  function puntoBajo(ev) {
    var el = document.elementFromPoint(ev.clientX, ev.clientY);
    var punto = el && el.closest ? el.closest(".acc-punto") : null;
    if (!punto || !grid.contains(punto)) return null;
    // Solo cuenta si el dedo está cerca del centro del punto.
    var r = punto.getBoundingClientRect();
    var dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height / 2);
    return Math.sqrt(dx * dx + dy * dy) <= r.width * 0.55 ? punto.getAttribute("data-id") : null;
  }
  function aCoordenadas(ev) {
    var r = grid.getBoundingClientRect();
    return { x: (ev.clientX - r.left) / r.width * 300, y: (ev.clientY - r.top) / r.height * 300 };
  }

  grid.addEventListener("pointerdown", function (ev) {
    var id = puntoBajo(ev);
    if (!id) return;
    ev.preventDefault();
    if (seleccion.length && seleccion.indexOf(id) < 0 && !dibujando) {
      // Tocar puntos uno por uno también funciona (sigue el patrón).
    }
    dibujando = true;
    try { grid.setPointerCapture(ev.pointerId); } catch (e) {}
    agregar(id);
    pintar();
  });
  grid.addEventListener("pointermove", function (ev) {
    if (!dibujando) return;
    ev.preventDefault();
    var id = puntoBajo(ev);
    if (id) agregar(id);
    puntoMovil = aCoordenadas(ev);
    pintar();
  });
  function terminar() {
    dibujando = false;
    puntoMovil = null;
    pintar();
  }
  grid.addEventListener("pointerup", terminar);
  grid.addEventListener("pointercancel", terminar);
  // Con teclado: Enter/Espacio en un punto lo agrega.
  grid.querySelectorAll(".acc-punto").forEach(function (p) {
    p.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); agregar(p.getAttribute("data-id")); pintar(); }
    });
  });

  var deshacer = document.getElementById("patronDeshacer");
  var limpiar = document.getElementById("patronLimpiar");
  if (deshacer) deshacer.addEventListener("click", function () { seleccion.pop(); pintar(); });
  if (limpiar) limpiar.addEventListener("click", function () { seleccion = []; pintar(); });

  // Al dibujar un patrón se marca solo el método «Patrón».
  grid.addEventListener("pointerup", function () {
    var chk = document.querySelector('input[name="tipo_bloqueo"][value="patron"]');
    if (chk && seleccion.length && !chk.checked) { chk.checked = true; chk.dispatchEvent(new Event("change")); }
  });
  pintar();
}

function inicializarCalculo() {
  var cot = document.getElementById("inputCotizacion");
  var pct = document.getElementById("inputRecargoPct");
  var outRecargo = document.getElementById("outRecargo");
  var outTotal = document.getElementById("outTotal");
  if (!cot || !pct) return;

  function recalcular() {
    var c = parseFloat(cot.value) || 0;
    var p = parseFloat(pct.value) || 0;
    if (c < 0) c = 0;
    if (p < 0) p = 0;
    var recargo = Math.round((c * p / 100) * 100) / 100;
    var total = Math.round((c + recargo) * 100) / 100;
    if (outRecargo) outRecargo.value = recargo.toFixed(2);
    if (outTotal) outTotal.value = total.toFixed(2);
  }
  cot.addEventListener("input", recalcular);
  pct.addEventListener("input", recalcular);
  recalcular();
}


function inicializarMarcaModelo() {
  var selectMarca = document.getElementById("selectMarca");
  var inputMarcaOtro = document.getElementById("inputMarcaOtro");
  var hiddenMarca = document.getElementById("hiddenMarca");
  var selectModelo = document.getElementById("selectModelo");
  var inputModeloOtro = document.getElementById("inputModeloOtro");
  var hiddenModelo = document.getElementById("hiddenModelo");
  if (!selectMarca || !selectModelo) return;

  var mapaModelos = window.MARCA_MODELOS || {};
  var marcaActual = window.ORDEN_MARCA_ACTUAL || "";
  var modeloActual = window.ORDEN_MODELO_ACTUAL || "";

  function poblarModelos(marca, modeloSeleccionado) {
    selectModelo.innerHTML = "";
    var modelos = mapaModelos[marca] || [];
    var opcionVacia = document.createElement("option");
    opcionVacia.value = "";
    opcionVacia.textContent = modelos.length ? "Selecciona un modelo..." : "Sin modelos precargados";
    selectModelo.appendChild(opcionVacia);
    var coincide = false;
    modelos.forEach(function (nombreModelo) {
      var opt = document.createElement("option");
      opt.value = nombreModelo;
      opt.textContent = nombreModelo;
      if (nombreModelo === modeloSeleccionado) { opt.selected = true; coincide = true; }
      selectModelo.appendChild(opt);
    });
    var opcionOtro = document.createElement("option");
    opcionOtro.value = "__otro__";
    opcionOtro.textContent = "Otro modelo (especificar)";
    selectModelo.appendChild(opcionOtro);

    if (modeloSeleccionado && !coincide) {
      opcionOtro.selected = true;
      inputModeloOtro.style.display = "block";
      inputModeloOtro.value = modeloSeleccionado;
    } else {
      inputModeloOtro.style.display = "none";
    }
    hiddenModelo.value = modeloSeleccionado || "";
  }

  function sincronizarMarca() {
    if (selectMarca.value === "__otro__") {
      inputMarcaOtro.style.display = "block";
      hiddenMarca.value = inputMarcaOtro.value;
      poblarModelos("", "");
    } else {
      inputMarcaOtro.style.display = "none";
      hiddenMarca.value = selectMarca.value;
      poblarModelos(selectMarca.value, "");
    }
  }

  function sincronizarModelo() {
    if (selectModelo.value === "__otro__") {
      inputModeloOtro.style.display = "block";
      hiddenModelo.value = inputModeloOtro.value;
    } else {
      inputModeloOtro.style.display = "none";
      hiddenModelo.value = selectModelo.value;
    }
  }

  // Estado inicial (nueva orden u orden existente)
  var opcionesMarca = Array.prototype.map.call(selectMarca.options, function (o) { return o.value; });
  if (marcaActual && opcionesMarca.indexOf(marcaActual) !== -1) {
    selectMarca.value = marcaActual;
    inputMarcaOtro.style.display = "none";
    poblarModelos(marcaActual, modeloActual);
  } else if (marcaActual) {
    selectMarca.value = "__otro__";
    inputMarcaOtro.style.display = "block";
    inputMarcaOtro.value = marcaActual;
    hiddenMarca.value = marcaActual;
    poblarModelos("", modeloActual);
    if (modeloActual) {
      inputModeloOtro.style.display = "block";
      inputModeloOtro.value = modeloActual;
    }
  } else {
    poblarModelos("", "");
  }

  selectMarca.addEventListener("change", sincronizarMarca);
  inputMarcaOtro.addEventListener("input", function () { hiddenMarca.value = inputMarcaOtro.value; });
  selectModelo.addEventListener("change", sincronizarModelo);
  inputModeloOtro.addEventListener("input", function () { hiddenModelo.value = inputModeloOtro.value; });
}


function inicializarServicioRapido() {
  var select = document.getElementById("selectServicioRapido");
  if (!select) return; // widget no presente en esta página

  var preview = document.getElementById("srPreview");
  var btnAplicar = document.getElementById("srAplicar");
  var btnAgregar = document.getElementById("srAgregar");
  var btnEditar = document.getElementById("srEditar");
  var btnBorrar = document.getElementById("srBorrar");

  var overlay = document.getElementById("srModalOverlay");
  var titulo = document.getElementById("srModalTitulo");
  var campoNombre = document.getElementById("srNombre");
  var campoFalla = document.getElementById("srFalla");
  var campoEstado = document.getElementById("srEstadoFisico");
  var campoObs = document.getElementById("srObservaciones");
  var campoTrabajo = document.getElementById("srTrabajo");
  var campoDias = document.getElementById("srDias");
  var campoCotizacion = document.getElementById("srCotizacion");
  var campoRecargo = document.getElementById("srRecargoPct");
  var modalError = document.getElementById("srModalError");
  var btnGuardar = document.getElementById("srGuardar");
  var btnCancelar = document.getElementById("srCancelar");

  var servicios = (window.SERVICIOS_RAPIDOS || []).slice();
  var modo = "crear";
  var idEnEdicion = null;

  function poblarSelect(idSeleccionar) {
    select.innerHTML = "";
    var vacia = document.createElement("option");
    vacia.value = "";
    vacia.textContent = servicios.length ? "Selecciona un servicio rápido..." : "No hay servicios rápidos guardados todavía";
    select.appendChild(vacia);
    servicios.forEach(function (s) {
      var opt = document.createElement("option");
      opt.value = String(s.id);
      opt.textContent = s.nombre;
      select.appendChild(opt);
    });
    if (idSeleccionar) select.value = String(idSeleccionar);
    actualizarPreview();
  }

  function servicioSeleccionado() {
    var id = parseInt(select.value, 10);
    if (!id) return null;
    for (var i = 0; i < servicios.length; i++) {
      if (servicios[i].id === id) return servicios[i];
    }
    return null;
  }

  function actualizarPreview() {
    var s = servicioSeleccionado();
    if (!s) { preview.textContent = ""; return; }
    var partes = [];
    if (s.falla_reportada) partes.push(s.falla_reportada);
    partes.push(s.dias_plazo + " día(s)");
    preview.textContent = partes.join(" · ");
  }

  function dispararInput(el) {
    if (!el) return;
    var ev;
    try { ev = new Event("input", { bubbles: true }); } catch (e) { ev = document.createEvent("Event"); ev.initEvent("input", true, true); }
    el.dispatchEvent(ev);
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function sumarDias(fechaBase, dias) {
    var partes = (fechaBase || "").split("-");
    var base;
    if (partes.length === 3) {
      base = new Date(parseInt(partes[0], 10), parseInt(partes[1], 10) - 1, parseInt(partes[2], 10));
    } else {
      base = new Date();
    }
    base.setDate(base.getDate() + (parseInt(dias, 10) || 0));
    return base.getFullYear() + "-" + pad2(base.getMonth() + 1) + "-" + pad2(base.getDate());
  }

  // servicioForzado: si se pasa (por ejemplo desde la sugerencia automática
  // del panda), se aplica ESE servicio sin importar cuál esté seleccionado
  // en la lista, y de paso se refleja la selección en el <select>.
  function aplicarServicio(servicioForzado) {
    var s = servicioForzado || servicioSeleccionado();
    if (!s) {
      preview.textContent = "Selecciona un servicio rápido de la lista antes de aplicar.";
      return;
    }
    if (servicioForzado) select.value = String(s.id);
    var campoFallaOrden = document.querySelector('textarea[name="falla_reportada"]');
    var campoEstadoOrden = document.querySelector('textarea[name="observaciones_condicion"]');
    var campoObsOrden = document.querySelector('textarea[name="observaciones"]');
    var campoTrabajoOrden = document.querySelector('textarea[name="trabajo_realizado"]');
    var campoFechaEntrega = document.querySelector('input[name="fecha_entrega"]');
    var campoCot = document.getElementById("inputCotizacion");
    var campoPct = document.getElementById("inputRecargoPct");

    if (campoFallaOrden) campoFallaOrden.value = s.falla_reportada || "";
    if (campoEstadoOrden) campoEstadoOrden.value = s.estado_fisico || "";
    if (campoObsOrden) campoObsOrden.value = s.observaciones || "";
    if (campoTrabajoOrden) campoTrabajoOrden.value = s.trabajo_realizado || "";

    if (campoFechaEntrega) {
      var base = window.ORDEN_FECHA_ENTRADA;
      if (!base) {
        var hoy = new Date();
        base = hoy.getFullYear() + "-" + pad2(hoy.getMonth() + 1) + "-" + pad2(hoy.getDate());
      }
      campoFechaEntrega.value = sumarDias(base, s.dias_plazo);
    }

    if (campoCot) { campoCot.value = s.cotizacion || 0; dispararInput(campoCot); }
    if (campoPct) { campoPct.value = s.recargo_pct || 0; dispararInput(campoPct); }

    preview.textContent = 'Aplicado: "' + s.nombre + '".';
  }

  function abrirModal(modoNuevo, servicio) {
    modo = modoNuevo;
    modalError.style.display = "none";
    modalError.textContent = "";
    if (modo === "editar" && servicio) {
      idEnEdicion = servicio.id;
      titulo.textContent = "Editar servicio rápido";
      campoNombre.value = servicio.nombre || "";
      campoFalla.value = servicio.falla_reportada || "";
      campoEstado.value = servicio.estado_fisico || "";
      campoObs.value = servicio.observaciones || "";
      campoTrabajo.value = servicio.trabajo_realizado || "";
      campoDias.value = servicio.dias_plazo || 0;
      campoCotizacion.value = servicio.cotizacion || 0;
      campoRecargo.value = servicio.recargo_pct || 0;
    } else {
      idEnEdicion = null;
      titulo.textContent = "Nuevo servicio rápido";
      campoNombre.value = "";
      campoFalla.value = "";
      campoEstado.value = "";
      campoObs.value = "";
      campoTrabajo.value = "";
      campoDias.value = 0;
      campoCotizacion.value = 0;
      campoRecargo.value = 0;
    }
    overlay.style.display = "flex";
    campoNombre.focus();
  }

  function cerrarModal() {
    cerrarModalConEfecto(overlay);
  }

  function guardarModal() {
    modalError.style.display = "none";
    var nombre = campoNombre.value.trim();
    if (!nombre) {
      modalError.textContent = "El nombre no puede estar vacío.";
      modalError.style.display = "block";
      return;
    }
    var datos = new URLSearchParams();
    datos.append("nombre", nombre);
    datos.append("falla_reportada", campoFalla.value);
    datos.append("estado_fisico", campoEstado.value);
    datos.append("observaciones", campoObs.value);
    datos.append("trabajo_realizado", campoTrabajo.value);
    datos.append("dias_plazo", campoDias.value || "0");
    datos.append("cotizacion", campoCotizacion.value || "0");
    datos.append("recargo_pct", campoRecargo.value || "0");

    var url = modo === "editar" ? ("/servicios-rapidos/" + idEnEdicion + "/editar") : "/servicios-rapidos";
    btnGuardar.disabled = true;
    fetch(url, { method: "POST", body: datos })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        btnGuardar.disabled = false;
        if (!data.ok) {
          modalError.textContent = data.error || "No se pudo guardar el servicio rápido.";
          modalError.style.display = "block";
          return;
        }
        var s = data.servicio;
        if (modo === "editar") {
          for (var i = 0; i < servicios.length; i++) {
            if (servicios[i].id === s.id) { servicios[i] = s; break; }
          }
        } else {
          servicios.push(s);
        }
        poblarSelect(s.id);
        cerrarModal();
      })
      .catch(function () {
        btnGuardar.disabled = false;
        modalError.textContent = "Error de conexión. Intenta de nuevo.";
        modalError.style.display = "block";
      });
  }

  function borrarSeleccionado() {
    var s = servicioSeleccionado();
    if (!s) {
      preview.textContent = "Selecciona un servicio rápido de la lista antes de borrar.";
      return;
    }
    if (!confirm('¿Borrar el servicio rápido "' + s.nombre + '"? Esta acción no se puede deshacer.')) return;
    fetch("/servicios-rapidos/" + s.id + "/eliminar", { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ok) {
          preview.textContent = data.error || "No se pudo borrar el servicio rápido.";
          return;
        }
        servicios = servicios.filter(function (x) { return x.id !== s.id; });
        poblarSelect("");
      })
      .catch(function () {
        preview.textContent = "Error de conexión. Intenta de nuevo.";
      });
  }

  select.addEventListener("change", actualizarPreview);
  if (btnAplicar) btnAplicar.addEventListener("click", function () { aplicarServicio(); });
  if (btnAgregar) btnAgregar.addEventListener("click", function () { abrirModal("crear", null); });
  if (btnEditar) btnEditar.addEventListener("click", function () {
    var s = servicioSeleccionado();
    if (!s) { preview.textContent = "Selecciona un servicio rápido de la lista antes de editar."; return; }
    abrirModal("editar", s);
  });
  if (btnBorrar) btnBorrar.addEventListener("click", borrarSeleccionado);
  if (btnGuardar) btnGuardar.addEventListener("click", guardarModal);
  if (btnCancelar) btnCancelar.addEventListener("click", cerrarModal);
  if (overlay) overlay.addEventListener("click", function (e) { if (e.target === overlay) cerrarModal(); });

  // ---------- Sugerencia automática: si lo que se escribió en "Falla
  // reportada" se parece a un servicio rápido ya guardado, el panda lo
  // sugiere con un botón para aplicarlo de una vez, en vez de tener que
  // buscarlo a mano en la lista. Comparación simple por palabras en común
  // (sin IA ni conexión externa), igual de "manual" que el resto del
  // asistente. ----------

  var sugeridosEstaCarga = {}; // ids de servicios ya sugeridos en esta página, para no insistir

  function normalizarParaComparar(s) {
    return (s || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function mejorServicioParaTexto(texto) {
    var textoNorm = normalizarParaComparar(texto);
    var palabras = textoNorm.split(/[^a-z0-9]+/).filter(function (p) { return p.length >= 4; });
    if (!palabras.length) return null;

    var mejor = null;
    var mejorPuntaje = 0;
    servicios.forEach(function (s) {
      var objetivo = normalizarParaComparar(s.nombre + " " + (s.falla_reportada || ""));
      var puntaje = 0;
      palabras.forEach(function (p) { if (objetivo.indexOf(p) !== -1) puntaje++; });
      if (puntaje > mejorPuntaje) { mejorPuntaje = puntaje; mejor = s; }
    });
    return mejorPuntaje >= 1 ? mejor : null;
  }

  function sugerirServicioRapidoSiAplica() {
    if (typeof window.pandaSugerir !== "function") return;
    var campoFallaOrden = document.querySelector('textarea[name="falla_reportada"]');
    if (!campoFallaOrden) return;
    var texto = campoFallaOrden.value.trim();
    if (texto.length < 8) return;

    var sugerido = mejorServicioParaTexto(texto);
    if (!sugerido || sugeridosEstaCarga[sugerido.id]) return;
    var actual = servicioSeleccionado();
    if (actual && actual.id === sugerido.id) return;

    var mostrado = window.pandaSugerir(
      'La falla se parece al servicio rápido "' + sugerido.nombre + '". ¿Lo aplico?',
      "Sí, aplicar",
      function () { aplicarServicio(sugerido); }
    );
    if (mostrado) sugeridosEstaCarga[sugerido.id] = true;
  }

  var campoFallaParaSugerir = document.querySelector('textarea[name="falla_reportada"]');
  if (campoFallaParaSugerir) {
    campoFallaParaSugerir.addEventListener("blur", sugerirServicioRapidoSiAplica);
  }

  poblarSelect("");
}

// Permite agregar accesorios/condiciones personalizados que no están en la
// lista rápida, sin perder la posibilidad de marcar varios a la vez.
function agregarChip(gridId, inputId, fieldName) {
  var input = document.getElementById(inputId);
  var grid = document.getElementById(gridId);
  if (!input || !grid) return;
  var valor = input.value.trim();
  if (!valor) return;

  var yaExiste = Array.prototype.some.call(
    grid.querySelectorAll("input[type=checkbox]"),
    function (chk) { return chk.value.toLowerCase() === valor.toLowerCase(); }
  );
  if (yaExiste) {
    var existente = Array.prototype.find.call(
      grid.querySelectorAll("input[type=checkbox]"),
      function (chk) { return chk.value.toLowerCase() === valor.toLowerCase(); }
    );
    if (existente) existente.checked = true;
    input.value = "";
    return;
  }

  var label = document.createElement("label");
  label.className = "checkbox-chip";
  var checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.name = fieldName;
  checkbox.value = valor;
  checkbox.checked = true;
  label.appendChild(checkbox);
  label.appendChild(document.createTextNode(" " + valor));
  grid.appendChild(label);

  input.value = "";
  input.focus();
}
