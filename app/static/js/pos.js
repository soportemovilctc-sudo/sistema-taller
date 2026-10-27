// Lógica del carrito del Punto de Venta.
var carrito = [];
var TASA_ISV = 15;
var COTIZACION_ID = null;

document.addEventListener("DOMContentLoaded", function () {
  var posLayout = document.querySelector(".pos-layout");
  if (posLayout) {
    var tasaAttr = parseFloat(posLayout.getAttribute("data-tasa-isv"));
    if (!isNaN(tasaAttr)) TASA_ISV = tasaAttr;
  }

  // Venta desde una cotización: precarga el carrito con sus productos.
  var cotEl = document.getElementById("posCotizacion");
  if (cotEl) {
    try {
      var cot = JSON.parse(cotEl.textContent);
      COTIZACION_ID = cot.id;
      (cot.items || []).forEach(function (it) {
        carrito.push({ id: it.id, nombre: it.nombre, categoria: it.categoria, precio: it.precio, precioLista: it.precioLista,
                       cantidad: Math.min(it.cantidad, it.existencia || it.cantidad), existencia: it.existencia });
      });
      setTimeout(renderCarrito, 0);
    } catch (e) {}
  }

  document.querySelectorAll(".product-card").forEach(function (card) {
    card.addEventListener("click", function () {
      agregarAlCarrito({
        id: parseInt(card.getAttribute("data-id"), 10),
        nombre: card.getAttribute("data-nombre"),
        categoria: card.getAttribute("data-categoria") || "",
        precio: parseFloat(card.getAttribute("data-precio")),
        existencia: parseInt(card.getAttribute("data-existencia"), 10),
      });
    });
  });

  var buscador = document.getElementById("posBuscarProducto");
  var catActiva = "";
  function filtrarProductos() {
    var q = buscador ? buscador.value.toLowerCase() : "";
    document.querySelectorAll(".product-card").forEach(function (card) {
      var texto = ((card.getAttribute("data-nombre") || "") + " " + (card.getAttribute("data-codigo") || "") + " " +
                   (card.getAttribute("data-categoria") || "")).toLowerCase();
      var okCat = !catActiva || card.getAttribute("data-categoria") === catActiva;
      card.style.display = (okCat && texto.includes(q)) ? "" : "none";
    });
  }
  if (buscador) buscador.addEventListener("input", filtrarProductos);
  document.querySelectorAll("#posCategorias .m-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      catActiva = chip.getAttribute("data-cat") || "";
      document.querySelectorAll("#posCategorias .m-chip").forEach(function (c) { c.classList.toggle("on", c === chip); });
      filtrarProductos();
    });
  });

  var descuentoInput = document.getElementById("posDescuento");
  if (descuentoInput) descuentoInput.addEventListener("input", actualizarTotales);
  var recibidoInput = document.getElementById("posMontoRecibido");
  if (recibidoInput) recibidoInput.addEventListener("input", actualizarTotales);
  var formaPagoSel = document.getElementById("posFormaPago");
  if (formaPagoSel) formaPagoSel.addEventListener("change", actualizarTotales);

  var finalizarBtn = document.getElementById("posFinalizar");
  if (finalizarBtn) finalizarBtn.addEventListener("click", finalizarVenta);

  var exacto = document.getElementById("posExacto");
  if (exacto) exacto.addEventListener("click", function () {
    var m = document.getElementById("posMontoRecibido");
    if (m) { m.value = totalesVenta().total.toFixed(2); actualizarTotales(); }
  });

  // Documento: comprobante interno o factura fiscal (con RTN opcional).
  var rtnPorCliente = {};
  try { rtnPorCliente = JSON.parse((document.getElementById("posClientesRtn") || {}).textContent || "{}"); } catch (e) {}
  function mostrarRtn() {
    var campo = document.getElementById("posCampoRtn");
    if (campo) campo.style.display = tipoDocumento() === "fiscal" ? "" : "none";
  }
  document.querySelectorAll('input[name="posTipoDoc"]').forEach(function (r) { r.addEventListener("change", mostrarRtn); });
  var cliSel = document.getElementById("posCliente");
  function rtnDelCliente() {
    var rtn = document.getElementById("posRtn");
    if (rtn && cliSel) rtn.value = rtnPorCliente[cliSel.value] || "";
  }
  if (cliSel) { cliSel.addEventListener("change", rtnDelCliente); if (window.jQuery) window.jQuery(cliSel).on("change", rtnDelCliente); }
  rtnDelCliente();
  mostrarRtn();

  renderCarrito();
});

function agregarAlCarrito(producto) {
  var existente = carrito.find(function (i) { return i.id === producto.id; });
  if (existente) {
    if (existente.cantidad < producto.existencia) existente.cantidad += 1;
  } else {
    carrito.push({ id: producto.id, nombre: producto.nombre, categoria: producto.categoria, precio: producto.precio, precioLista: producto.precio, cantidad: 1, existencia: producto.existencia });
  }
  renderCarrito();
}

function cambiarCantidad(id, delta) {
  var item = carrito.find(function (i) { return i.id === id; });
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad > item.existencia) item.cantidad = item.existencia;
  if (item.cantidad <= 0) {
    carrito = carrito.filter(function (i) { return i.id !== id; });
  }
  renderCarrito();
}

function quitarDelCarrito(id) {
  carrito = carrito.filter(function (i) { return i.id !== id; });
  renderCarrito();
}

// Cambia el precio de venta de una línea del carrito (el cajero lo puede
// ajustar aquí mismo, por ejemplo si el precio del catálogo quedó
// configurado como el de costo). Solo recalcula los totales, sin
// reconstruir las filas del carrito, para no perder el foco del campo
// mientras se está escribiendo.
function cambiarPrecio(id, valorTexto) {
  var item = carrito.find(function (i) { return i.id === id; });
  if (!item) return;
  var valor = parseFloat(valorTexto);
  if (isNaN(valor) || valor < 0) valor = 0;
  item.precio = valor;
  var fila = document.querySelector('.cart-item[data-id="' + id + '"]');
  if (fila) {
    var conIsv = fila.querySelector(".cart-precio-isv");
    if (conIsv) conIsv.textContent = "con ISV L " + (valor * (1 + TASA_ISV / 100)).toFixed(2);
    fila.classList.toggle("precio-cambiado", Math.abs(valor - item.precioLista) > 0.004);
  }
  actualizarTotales();
}

function renderCarrito() {
  var lista = document.getElementById("carritoLista");
  if (!lista) return;
  lista.innerHTML = "";

  if (carrito.length === 0) {
    lista.innerHTML = '<div class="empty-state">El carrito está vacío. Toca un producto para agregarlo.</div>';
  }

  carrito.forEach(function (item) {
    var row = document.createElement("div");
    row.className = "cart-item" + (Math.abs(item.precio - item.precioLista) > 0.004 ? " precio-cambiado" : "");
    row.setAttribute("data-id", item.id);
    var nombreSeguro = document.createElement("span");
    nombreSeguro.textContent = item.nombre;
    var catSegura = document.createElement("span");
    catSegura.textContent = item.categoria || "";
    row.innerHTML =
      '<span class="name">' + (item.categoria ? '<small class="cart-cat">' + catSegura.innerHTML + '</small>' : '') + nombreSeguro.innerHTML +
        '<label class="cart-precio"><span>Precio c/u (sin ISV)</span>' +
        '<input type="number" min="0" step="0.01" class="cart-price-input" value="' + item.precio.toFixed(2) +
        '" oninput="cambiarPrecio(' + item.id + ', this.value)" aria-label="Precio de ' + nombreSeguro.innerHTML + '"></label>' +
        '<small class="cart-precio-isv">con ISV L ' + (item.precio * (1 + TASA_ISV / 100)).toFixed(2) + '</small>' +
        '<small class="cart-precio-lista">Precio del inventario: L ' + item.precioLista.toFixed(2) + '</small></span>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', -1)">-</button>' +
      '<input type="number" min="1" value="' + item.cantidad + '" readonly>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', 1)">+</button>' +
      '<button type="button" class="btn btn-danger btn-sm" onclick="quitarDelCarrito(' + item.id + ')">x</button>';
    lista.appendChild(row);
  });

  actualizarTotales();
}

// Redondeo a centavos igual que el servidor (ROUND_HALF_UP). Sin esto el
// total quedaba en 600.001 aunque en pantalla dijera 600.00, y al escribir
// 600 en «Monto recibido» el botón de Efectivo no se activaba.
function r2(n) { return Math.round((Number(n) + (n >= 0 ? 1e-9 : -1e-9)) * 100) / 100; }

function totalesVenta() {
  var subtotal = 0;
  carrito.forEach(function (item) { subtotal += r2(r2(item.precio) * item.cantidad); });
  subtotal = r2(subtotal);
  var descuento = r2(parseFloat((document.getElementById("posDescuento") || {}).value) || 0);
  if (descuento < 0) descuento = 0;
  if (descuento > subtotal) descuento = subtotal;
  var totalNeto = r2(subtotal - descuento);
  var total = r2(totalNeto * (1 + TASA_ISV / 100));
  return { subtotal: subtotal, totalNeto: totalNeto, total: total, isv: r2(total - totalNeto) };
}

function actualizarTotales() {
  var t = totalesVenta();
  var subtotal = t.subtotal, isv = t.isv, total = t.total;
  var esEfectivoPos = ((document.getElementById("posFormaPago") || {}).value || "Efectivo") === "Efectivo";
  var recibido = esEfectivoPos ? r2(parseFloat((document.getElementById("posMontoRecibido") || {}).value) || 0) : total;
  var cambio = r2(recibido - total);

  setTexto("posSubtotal", subtotal.toFixed(2));
  setTexto("posIsv", isv.toFixed(2));
  setTexto("posTotal", total.toFixed(2));
  setTexto("posCambio", (cambio > 0 ? cambio : 0).toFixed(2));

  var finalizarBtn = document.getElementById("posFinalizar");
  if (finalizarBtn) finalizarBtn.disabled = carrito.length === 0 || recibido < total;
  var falta = document.getElementById("posFalta");
  if (falta) falta.textContent = (esEfectivoPos && carrito.length && recibido < total) ? "Escribe cuánto entregó el cliente (o toca «Exacto»)." : "";
}

function tipoDocumento() {
  var r = document.querySelector('input[name="posTipoDoc"]:checked');
  return r ? r.value : "interno";
}

function setTexto(id, texto) {
  var el = document.getElementById(id);
  if (el) el.textContent = texto;
}

function finalizarVenta() {
  var payload = {
    items: carrito.map(function (i) { return { producto_id: i.id, cantidad: i.cantidad, precio_unitario: i.precio }; }),
    descuento: parseFloat((document.getElementById("posDescuento") || {}).value) || 0,
    forma_pago: (document.getElementById("posFormaPago") || {}).value || "Efectivo",
    monto_recibido: parseFloat((document.getElementById("posMontoRecibido") || {}).value) || 0,
    cliente_id: (document.getElementById("posCliente") || {}).value || null,
    cotizacion_id: COTIZACION_ID,
    tipo_documento: tipoDocumento(),
    cliente_rtn: tipoDocumento() === "fiscal" ? ((document.getElementById("posRtn") || {}).value || "") : "",
  };
  var btnFin = document.getElementById("posFinalizar");
  if (btnFin) { if (btnFin.dataset.enviando) return; btnFin.dataset.enviando = "1"; btnFin.disabled = true; }
  var mensajeEl = document.getElementById("posMensaje");

  fetch("/pos/vender", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); })
    .then(function (res) {
      if (btnFin) delete btnFin.dataset.enviando;
      if (res.data.ok) {
        if (mensajeEl) {
          mensajeEl.className = "";
          var resumen = document.createElement("div");
          resumen.className = "flash flash-success";
          var esFiscal = res.data.tipo_documento === "fiscal";
          resumen.textContent = "Venta " + res.data.numero_venta + " registrada · " + (esFiscal ? "Factura fiscal " : "Comprobante ") +
            (res.data.numero_documento || "") + ". Cambio: L " + res.data.cambio.toFixed(2);
          mensajeEl.innerHTML = "";
          mensajeEl.appendChild(resumen);
          if (window.pandaReaccionEvento) window.pandaReaccionEvento("venta", res.data.numero_venta);

          if (res.data.factura_id) {
            var acciones = document.createElement("div");
            acciones.style.cssText = "display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;";
            acciones.innerHTML =
              '<a href="/facturas/' + res.data.factura_id + '/pdf/tirilla" target="_blank" class="btn btn-success btn-sm">Imprimir ' + (esFiscal ? "factura" : "comprobante") + ' (tirilla)</a>' +
              '<a href="/facturas/' + res.data.factura_id + '/pdf" target="_blank" class="btn btn-outline btn-sm">Ver ' + (esFiscal ? "factura" : "comprobante") + ' (PDF carta)</a>' +
              '<button type="button" class="btn btn-primary btn-sm" id="posNuevaVenta">Nueva venta</button>';
            mensajeEl.appendChild(acciones);
            var btnNueva = document.getElementById("posNuevaVenta");
            if (btnNueva) btnNueva.addEventListener("click", function () { window.location.reload(); });
            // Intenta abrir la tirilla automáticamente para imprimir de una
            // vez; si el navegador bloquea la ventana emergente, el botón de
            // arriba sigue disponible para abrirla manualmente.
            window.open("/facturas/" + res.data.factura_id + "/pdf/tirilla", "_blank");
          }
        }
        carrito = [];
        COTIZACION_ID = null;
        renderCarrito();
        var recibidoInput = document.getElementById("posMontoRecibido");
        if (recibidoInput) recibidoInput.value = "";
      } else {
        actualizarTotales();
        if (mensajeEl) {
          mensajeEl.className = "flash flash-error";
          mensajeEl.textContent = res.data.mensaje || "No se pudo completar la venta.";
        }
      }
    })
    .catch(function () {
      if (btnFin) { delete btnFin.dataset.enviando; actualizarTotales(); }
      if (mensajeEl) {
        mensajeEl.className = "flash flash-error";
        mensajeEl.textContent = "Error de conexión al procesar la venta.";
      }
    });
}
