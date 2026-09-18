// Lógica del formulario de Orden de Servicio: PIN numérico, patrón y cálculo financiero en vivo.
document.addEventListener("DOMContentLoaded", function () {
  inicializarPin();
  inicializarPatron();
  inicializarCalculo();
  inicializarMarcaModelo();
  inicializarServicioRapido();
});

function inicializarPin() {
  var display = document.getElementById("pinDisplay");
  var hidden = document.getElementById("pinValor");
  var pad = document.getElementById("pinPad");
  var toggleBtn = document.getElementById("pinToggleVer");
  if (!pad || !hidden || !display) return;

  var oculto = true;

  function actualizarDisplay() {
    var valor = hidden.value || "";
    display.textContent = valor ? (oculto ? "•".repeat(valor.length) : valor) : "Sin PIN";
  }

  pad.querySelectorAll("button[data-num]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if ((hidden.value || "").length >= 12) return;
      hidden.value = (hidden.value || "") + btn.getAttribute("data-num");
      actualizarDisplay();
    });
  });
  var borrarBtn = document.getElementById("pinBorrar");
  var limpiarBtn = document.getElementById("pinLimpiar");
  if (borrarBtn) borrarBtn.addEventListener("click", function () {
    hidden.value = (hidden.value || "").slice(0, -1);
    actualizarDisplay();
  });
  if (limpiarBtn) limpiarBtn.addEventListener("click", function () {
    hidden.value = "";
    actualizarDisplay();
  });
  if (toggleBtn) toggleBtn.addEventListener("click", function () {
    oculto = !oculto;
    toggleBtn.textContent = oculto ? "Mostrar" : "Ocultar";
    actualizarDisplay();
  });
  actualizarDisplay();
}

function inicializarPatron() {
  var grid = document.getElementById("patronGrid");
  var hidden = document.getElementById("patronValor");
  var display = document.getElementById("patronDisplay");
  if (!grid || !hidden) return;

  var seleccion = (hidden.value || "").split(",").filter(Boolean);

  function pintar() {
    grid.querySelectorAll(".patron-dot").forEach(function (dot) {
      dot.classList.toggle("active", seleccion.includes(dot.getAttribute("data-id")));
    });
    if (display) display.textContent = seleccion.length ? ("Patrón: " + seleccion.join(" - ")) : "Sin patrón";
    hidden.value = seleccion.join(",");
  }

  grid.querySelectorAll(".patron-dot").forEach(function (dot) {
    dot.addEventListener("click", function () {
      var id = dot.getAttribute("data-id");
      var idx = seleccion.indexOf(id);
      if (idx >= 0) {
        seleccion = seleccion.slice(0, idx); // deshacer desde ese punto
      } else {
        seleccion.push(id);
      }
      pintar();
    });
  });
  var limpiarBtn = document.getElementById("patronLimpiar");
  if (limpiarBtn) limpiarBtn.addEventListener("click", function () {
    seleccion = [];
    pintar();
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

  function aplicarServicio() {
    var s = servicioSeleccionado();
    if (!s) {
      preview.textContent = "Selecciona un servicio rápido de la lista antes de aplicar.";
      return;
    }
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
    overlay.style.display = "none";
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
  if (btnAplicar) btnAplicar.addEventListener("click", aplicarServicio);
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
