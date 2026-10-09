// Lógica del formulario de Orden de Servicio: PIN numérico, patrón y cálculo financiero en vivo.
document.addEventListener("DOMContentLoaded", function () {
  inicializarPin();
  inicializarPatron();
  inicializarCalculo();
  inicializarMarcaModelo();
  inicializarServicioRapido();
  inicializarValidacionEnvio();
  inicializarAtajosCondicion();
});

// Marca exactamente los valores dados en un grid de chips (checkbox-chip),
// desmarcando primero el resto. Si algún valor no existe todavía como chip
// en ese grid, lo crea ya marcado (igual que "+ Agregar", pero en lote).
// La usan tanto el botón "Sin daños visibles" como aplicar un Servicio
// rápido que trae su propia Condición/Accesorios guardados.
function aplicarChips(gridId, valores) {
  var grid = document.getElementById(gridId);
  if (!grid) return;
  var lista = (valores || []).filter(Boolean);
  var checkboxes = Array.prototype.slice.call(grid.querySelectorAll("input[type=checkbox]"));
  var fieldName = checkboxes.length ? checkboxes[0].name : (gridId === "condicionGrid" ? "condicion" : "accesorios");
  checkboxes.forEach(function (chk) { chk.checked = false; });
  lista.forEach(function (valor) {
    var existente = checkboxes.filter(function (chk) { return chk.value.toLowerCase() === valor.toLowerCase(); })[0];
    if (existente) {
      existente.checked = true;
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
    checkboxes.push(checkbox);
  });
}

// Botón de un clic para el caso más común: equipo recibido en buen estado.
function inicializarAtajosCondicion() {
  var btn = document.getElementById("condicionSinDanos");
  if (!btn) return;
  btn.addEventListener("click", function () {
    aplicarChips("condicionGrid", ["Sin daños visibles"]);
  });
}

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

    // Condición/Accesorios son opcionales en la plantilla: si no trae nada
    // guardado, no se toca lo que ya esté marcado en la orden.
    if (s.condicion && s.condicion.length) aplicarChips("condicionGrid", s.condicion);
    if (s.accesorios && s.accesorios.length) aplicarChips("accesoriosGrid", s.accesorios);

    preview.textContent = 'Aplicado: "' + s.nombre + '".';
  }

  function marcarChipsModal(gridId, valores) {
    var grid = document.getElementById(gridId);
    if (!grid) return;
    var set = (valores || []).map(function (v) { return v.toLowerCase(); });
    grid.querySelectorAll("input[type=checkbox]").forEach(function (chk) {
      chk.checked = set.indexOf(chk.value.toLowerCase()) !== -1;
    });
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
      marcarChipsModal("srCondicionGrid", servicio.condicion);
      marcarChipsModal("srAccesoriosGrid", servicio.accesorios);
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
      marcarChipsModal("srCondicionGrid", []);
      marcarChipsModal("srAccesoriosGrid", []);
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
    document.querySelectorAll("#srCondicionGrid input[type=checkbox]:checked").forEach(function (chk) {
      datos.append("condicion", chk.value);
    });
    document.querySelectorAll("#srAccesoriosGrid input[type=checkbox]:checked").forEach(function (chk) {
      datos.append("accesorios", chk.value);
    });

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
