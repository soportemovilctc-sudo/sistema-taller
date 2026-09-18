// Lógica del carrito del Punto de Venta.
var carrito = [];

document.addEventListener("DOMContentLoaded", function () {
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
  if (descuentoInput) descuentoInput.addEventListener("input", renderCarrito);
  var recibidoInput = document.getElementById("posMontoRecibido");
  if (recibidoInput) recibidoInput.addEventListener("input", renderCarrito);

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

function renderCarrito() {
  var lista = document.getElementById("carritoLista");
  if (!lista) return;
  lista.innerHTML = "";
  var subtotal = 0;

  if (carrito.length === 0) {
    lista.innerHTML = '<div class="empty-state">El carrito está vacío. Toca un producto para agregarlo.</div>';
  }

  carrito.forEach(function (item) {
    var sub = item.precio * item.cantidad;
    subtotal += sub;
    var row = document.createElement("div");
    row.className = "cart-item";
    row.innerHTML =
      '<span class="name">' + item.nombre + '<br><small>L ' + item.precio.toFixed(2) + ' c/u</small></span>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', -1)">-</button>' +
      '<input type="number" min="1" value="' + item.cantidad + '" readonly>' +
      '<button type="button" class="btn btn-outline btn-sm" onclick="cambiarCantidad(' + item.id + ', 1)">+</button>' +
      '<button type="button" class="btn btn-danger btn-sm" onclick="quitarDelCarrito(' + item.id + ')">x</button>';
    lista.appendChild(row);
  });

  var descuento = parseFloat((document.getElementById("posDescuento") || {}).value) || 0;
  if (descuento < 0) descuento = 0;
  if (descuento > subtotal) descuento = subtotal;
  var total = subtotal - descuento;
  var recibido = parseFloat((document.getElementById("posMontoRecibido") || {}).value) || 0;
  var cambio = recibido - total;

  setTexto("posSubtotal", subtotal.toFixed(2));
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
    items: carrito.map(function (i) { return { producto_id: i.id, cantidad: i.cantidad }; }),
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
          mensajeEl.className = "flash flash-success";
          mensajeEl.textContent = "Venta " + res.data.numero_venta + " registrada. Cambio: L " + res.data.cambio.toFixed(2);
        }
        carrito = [];
        renderCarrito();
        var recibidoInput = document.getElementById("posMontoRecibido");
        if (recibidoInput) recibidoInput.value = "";
        setTimeout(function () { window.location.reload(); }, 1800);
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
