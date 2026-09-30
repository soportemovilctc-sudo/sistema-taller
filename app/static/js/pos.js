// Lógica del carrito del Punto de Venta.
var carrito = [];
var TASA_ISV = 15;

document.addEventListener("DOMContentLoaded", function () {
  var posLayout = document.querySelector(".pos-layout");
  if (posLayout) {
    var tasaAttr = parseFloat(posLayout.getAttribute("data-tasa-isv"));
    if (!isNaN(tasaAttr)) TASA_ISV = tasaAttr;
  }

  document.querySelectorAll(".product-card").forEach(function (card) {
    card.addEventListener("click", function () {
      agregarAlCarrito({
        id: parseInt(card.getAttribute("data-id"), 10),
        nombre: card.getAttribute("data-nombre"),
        precio: parseFloat(card.getAttribute("data-precio")),
        existencia: parseInt(card.getAttribute("data-existencia"), 10),
      });
    });
  });

  var buscador = document.getElementById("posBuscarProducto");
  if (buscador) {
    buscador.addEventListener("input", function () {
      var q = buscador.value.toLowerCase();
      document.querySelectorAll(".product-card").forEach(function (card) {
        var nombre = (card.getAttribute("data-nombre") || "").toLowerCase();
        card.style.display = nombre.includes(q) ? "" : "none";
      });
    });
  }

  var descuentoInput = document.getElementById("posDescuento");
  if (descuentoInput) descuentoInput.addEventListener("input", actualizarTotales);
  var recibidoInput = document.getElementById("posMontoRecibido");
  if (recibidoInput) recibidoInput.addEventListener("input", actualizarTotales);

  var finalizarBtn = document.getElementById("posFinalizar");
  if (finalizarBtn) finalizarBtn.addEventListener("click", finalizarVenta);

  renderCarrito();
});

function agregarAlCarrito(producto) {
  var existente = carrito.find(function (i) { return i.id === producto.id; });
  if (existente) {
    if (existente.cantidad < producto.existencia) existente.cantidad += 1;
  } else {
    carrito.push({ id: producto.id, nombre: producto.nombre, precio: producto.precio, cantidad: 1, existencia: producto.existencia });
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
    row.className = "cart-item";
    row.innerHTML =
      '<span class="name">' + item.nombre + '<br><small>L ' +
        '<input type="number" min="0" step="0.01" class="cart-price-input" value="' + item.precio.toFixed(2) +
        '" oninput="cambiarPrecio(' + item.id + ', this.value)"> c/u</small></span>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', -1)">-</button>' +
      '<input type="number" min="1" value="' + item.cantidad + '" readonly>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', 1)">+</button>' +
      '<button type="button" class="btn btn-danger btn-sm" onclick="quitarDelCarrito(' + item.id + ')">x</button>';
    lista.appendChild(row);
  });

  actualizarTotales();
}

function actualizarTotales() {
  var subtotal = 0;
  carrito.forEach(function (item) { subtotal += item.precio * item.cantidad; });

  var descuento = parseFloat((document.getElementById("posDescuento") || {}).value) || 0;
  if (descuento < 0) descuento = 0;
  if (descuento > subtotal) descuento = subtotal;
  var totalNeto = subtotal - descuento;
  var isv = totalNeto * TASA_ISV / 100;
  var total = totalNeto + isv;
  var recibido = parseFloat((document.getElementById("posMontoRecibido") || {}).value) || 0;
  var cambio = recibido - total;

  setTexto("posSubtotal", subtotal.toFixed(2));
  setTexto("posIsv", isv.toFixed(2));
  setTexto("posTotal", total.toFixed(2));
  setTexto("posCambio", (cambio > 0 ? cambio : 0).toFixed(2));

  var finalizarBtn = document.getElementById("posFinalizar");
  if (finalizarBtn) finalizarBtn.disabled = carrito.length === 0 || recibido < total;
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
  };
  var mensajeEl = document.getElementById("posMensaje");

  fetch("/pos/vender", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); })
    .then(function (res) {
      if (res.data.ok) {
        if (mensajeEl) {
          mensajeEl.className = "";
          var resumen = document.createElement("div");
          resumen.className = "flash flash-success";
          resumen.textContent = "Venta " + res.data.numero_venta + " registrada. Cambio: L " + res.data.cambio.toFixed(2);
          mensajeEl.innerHTML = "";
          mensajeEl.appendChild(resumen);
          if (window.pandaReaccionEvento) window.pandaReaccionEvento("venta", res.data.numero_venta);

          if (res.data.factura_id) {
            var acciones = document.createElement("div");
            acciones.style.cssText = "display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;";
            acciones.innerHTML =
              '<a href="/facturas/' + res.data.factura_id + '/pdf/tirilla" target="_blank" class="btn btn-success btn-sm">Imprimir recibo (tirilla)</a>' +
              '<a href="/facturas/' + res.data.factura_id + '/pdf" target="_blank" class="btn btn-outline btn-sm">Ver recibo (PDF carta)</a>' +
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
        renderCarrito();
        var recibidoInput = document.getElementById("posMontoRecibido");
        if (recibidoInput) recibidoInput.value = "";
      } else {
        if (mensajeEl) {
          mensajeEl.className = "flash flash-error";
          mensajeEl.textContent = res.data.mensaje || "No se pudo completar la venta.";
        }
      }
    })
    .catch(function () {
      if (mensajeEl) {
        mensajeEl.className = "flash flash-error";
        mensajeEl.textContent = "Error de conexión al procesar la venta.";
      }
    });
}
