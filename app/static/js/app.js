// Funciones generales de la interfaz: menú móvil y búsqueda global.
document.addEventListener("DOMContentLoaded", function () {
  var toggle = document.getElementById("menuToggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () {
      sidebar.classList.toggle("open");
    });
  }

  // Cerrar flashes automáticamente
  document.querySelectorAll(".flash").forEach(function (el) {
    setTimeout(function () { el.style.display = "none"; }, 6000);
  });

  // Búsqueda global
  var input = document.getElementById("globalSearch");
  var resultsBox = document.getElementById("searchResults");
  if (input && resultsBox) {
    var timeoutId = null;
    input.addEventListener("input", function () {
      var q = input.value.trim();
      clearTimeout(timeoutId);
      if (q.length < 2) {
        resultsBox.classList.remove("show");
        resultsBox.innerHTML = "";
        return;
      }
      timeoutId = setTimeout(function () {
        fetch("/api/buscar?q=" + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var html = "";
            if (data.ordenes && data.ordenes.length) {
              html += '<div class="grp-title">Órdenes</div>';
              data.ordenes.forEach(function (o) {
                html += '<a href="/ordenes/' + o.id + '"><b>' + o.numero_orden + '</b> · ' + o.cliente + ' · ' + o.equipo + ' · ' + o.estado + '</a>';
              });
            }
            if (data.clientes && data.clientes.length) {
              html += '<div class="grp-title">Clientes</div>';
              data.clientes.forEach(function (c) {
                html += '<a href="/clientes/' + c.id + '">' + c.nombre + ' · ' + (c.telefono || '') + '</a>';
              });
            }
            if (!html) { html = '<div class="grp-title">Sin resultados</div>'; }
            resultsBox.innerHTML = html;
            resultsBox.classList.add("show");
          });
      }, 250);
    });
    document.addEventListener("click", function (e) {
      if (!resultsBox.contains(e.target) && e.target !== input) {
        resultsBox.classList.remove("show");
      }
    });
  }
});

// Buscador con autocompletado para selects largos (clientes, repuestos,
// etc.): convierte cualquier <select class="js-buscar-select"> en un campo
// de texto con sugerencias en vivo (filtra mientras se escribe), sin
// cambiar cómo se envía el formulario: el <select> original sigue
// existiendo (oculto) y es el que se manda con el name/value de siempre
// (cliente_id, producto_id, etc.), con sus atributos data-* intactos
// (p. ej. data-precio) para que el resto del código del formulario siga
// funcionando igual que con un <select> normal.
function normalizarTextoBusqueda(s) {
  return (s || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Inicializa el buscador en UN <select>. Se puede llamar de nuevo para un
// select agregado dinámicamente (p. ej. al clonar una fila de repuestos);
// si ya estaba inicializado, no hace nada.
function inicializarBuscadorSelect(select) {
  if (!select || select.dataset.buscarListo) return;
  select.dataset.buscarListo = "1";

  var wrap = document.createElement("div");
  wrap.className = "buscar-select-wrap";

  var input = document.createElement("input");
  input.type = "text";
  input.className = "buscar-select-input";
  input.setAttribute("autocomplete", "off");
  input.placeholder = select.getAttribute("data-placeholder") || "Escribe para buscar...";

  var lista = document.createElement("div");
  lista.className = "buscar-select-resultados";

  select.parentNode.insertBefore(wrap, select);
  wrap.appendChild(input);
  wrap.appendChild(lista);
  wrap.appendChild(select);
  select.style.display = "none";

  function opciones() {
    return Array.prototype.slice.call(select.options).filter(function (o) { return o.value; });
  }

  function textoDe(valor) {
    var encontrada = null;
    opciones().some(function (o) { if (o.value === valor) { encontrada = o; return true; } return false; });
    return encontrada ? encontrada.textContent : "";
  }

  function sincronizarDesdeSelect() {
    input.value = select.value ? textoDe(select.value) : "";
    input.classList.remove("buscar-select-error");
  }

  function ocultarLista() {
    lista.classList.remove("show");
    lista.innerHTML = "";
  }

  function mostrarResultados(items) {
    if (!items.length) {
      lista.innerHTML = '<div class="buscar-select-vacio">Sin coincidencias</div>';
      lista.classList.add("show");
      return;
    }
    lista.innerHTML = "";
    items.slice(0, 30).forEach(function (op) {
      var item = document.createElement("div");
      item.className = "buscar-select-item";
      item.textContent = op.textContent;
      item.addEventListener("mousedown", function (e) {
        e.preventDefault();
        select.value = op.value;
        input.value = op.textContent;
        input.classList.remove("buscar-select-error");
        ocultarLista();
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      lista.appendChild(item);
    });
    lista.classList.add("show");
  }

  function filtrar(q) {
    if (!q) return opciones();
    return opciones().filter(function (o) {
      return normalizarTextoBusqueda(o.textContent).indexOf(q) !== -1;
    });
  }

  input.addEventListener("input", function () {
    if (select.value && textoDe(select.value) !== input.value) {
      select.value = "";
    }
    mostrarResultados(filtrar(normalizarTextoBusqueda(input.value.trim())));
  });

  input.addEventListener("focus", function () {
    mostrarResultados(filtrar(normalizarTextoBusqueda(input.value.trim())));
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { ocultarLista(); input.blur(); }
    if (e.key === "Enter") {
      e.preventDefault();
      var primero = lista.querySelector(".buscar-select-item");
      if (primero) primero.dispatchEvent(new Event("mousedown"));
    }
  });

  input.addEventListener("blur", function () {
    setTimeout(function () {
      sincronizarDesdeSelect();
      ocultarLista();
    }, 150);
  });

  select.addEventListener("change", sincronizarDesdeSelect);

  document.addEventListener("click", function (e) {
    if (!wrap.contains(e.target)) ocultarLista();
  });

  sincronizarDesdeSelect();
}
window.inicializarBuscadorSelect = inicializarBuscadorSelect;

function inicializarBuscadoresSelect() {
  document.querySelectorAll("select.js-buscar-select").forEach(inicializarBuscadorSelect);

  document.querySelectorAll("select.js-buscar-select[required]").forEach(function (select) {
    var form = select.closest("form");
    if (!form || form.dataset.validacionBuscarLista) return;
    form.dataset.validacionBuscarLista = "1";
    form.addEventListener("submit", function (e) {
      var faltantes = Array.prototype.slice.call(form.querySelectorAll("select.js-buscar-select[required]"))
        .filter(function (s) { return !s.value; });
      if (!faltantes.length) return;
      e.preventDefault();
      var faltante = faltantes[0];
      var wrapFaltante = faltante.closest(".buscar-select-wrap");
      var inputFaltante = wrapFaltante ? wrapFaltante.querySelector(".buscar-select-input") : null;
      if (inputFaltante) {
        inputFaltante.classList.add("buscar-select-error");
        inputFaltante.focus();
      }
      alert("Selecciona " + (faltante.getAttribute("data-entidad") || "una opción") + " de la lista antes de continuar.");
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  inicializarBuscadoresSelect();
});

function claseBadgeEstado(estado) {
  return "badge badge-" + estado.toLowerCase().replace(/ /g, "-");
}

// Menú "más opciones" de la barra de acciones fija (detalle de orden y
// cualquier otra página que use .action-bar-more).
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".action-bar-more > button").forEach(function (btn) {
    var menu = btn.parentElement.querySelector(".action-bar-more-menu");
    if (!menu) return;
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      menu.classList.toggle("show");
    });
  });
  document.addEventListener("click", function () {
    document.querySelectorAll(".action-bar-more-menu.show").forEach(function (m) { m.classList.remove("show"); });
  });
});


// Mascota panda del usuario de Caja (rol vendedor): se puede arrastrar a
// cualquier parte de la pantalla con mouse o dedo, y recuerda en
// localStorage dónde quedó para que siga ahí al cambiar de página (el
// sistema recarga toda la página en cada navegación, no es un SPA).
//
// Interacción:
//   - toque/clic CORTO (sin arrastrar)   -> reacción al azar (ver REACCIONES)
//   - toque MANTENIDO (sin arrastrar)    -> abre el globo del asistente (consejo/vencidas al azar)
//   - arrastre                            -> mueve al panda (como antes)
//
// Además de lo anterior, el panda ahora es más "activo": de vez en cuando
// aparece solo (sin que lo toquen) para avisar algo -vencidas, un saludo,
// un consejo-, reacciona cuando se acaba de registrar un pago/orden/factura
// (lee el mensaje flash que ya deja el servidor), muestra un resumen del
// cliente en cuanto se selecciona uno en Nueva Orden/POS, sugiere frases
// ya usadas antes al describir la falla, avisa si el nombre de un cliente
// nuevo se parece a uno que ya existe, y avisa si el precio de un repuesto
// va a quedar por debajo de su costo. Todo con contenido fijo (sin conexión
// a ningún modelo de IA), igual que antes.
function inicializarPandaMascota() {
  var panda = document.getElementById("pandaCajaMascota");
  if (!panda) return;

  var CLAVE_POSICION = "pandaCajaPos";
  var CLAVE_SALUDO_RICHARD = "pandaSaludoRichardFecha";
  var UMBRAL_ARRASTRE = 6; // px de movimiento antes de considerarlo arrastre y no un toque
  var UMBRAL_PRESION_LARGA = 480; // ms sostenido sin arrastrar, para abrir el asistente

  // Cada reacción es la lista de ids de los <animate>/<animateTransform>
  // (begin="indefinite" en el SVG de base.html) que hay que disparar
  // juntos para verla completa.
  var REACCIONES = [
    ["reaccionSaltoAnim"],
    ["reaccionGiroAnim"],
    ["reaccionGuinoAnim"],
    ["reaccionCorazonMov", "reaccionCorazonOpacidad"]
  ];

  function dispararReaccionAleatoria() {
    var elegida = REACCIONES[Math.floor(Math.random() * REACCIONES.length)];
    elegida.forEach(function (id) {
      var el = document.getElementById(id);
      if (el && typeof el.beginElement === "function") {
        try { el.beginElement(); } catch (e) { /* navegador sin soporte SMIL: no pasa nada */ }
      }
    });
  }

  // ---------- Asistente: consejos por página + soluciones + motivación ----------
  // Bastante más variado que antes para que no se sienta repetitivo.

  var ASISTENTE_TIPS = {
    "/": [
      "Desde el Dashboard puedes ver de un vistazo cuántas órdenes están listas para entregar y cuáles llevan más días de la cuenta.",
      "Los números del Dashboard son del día de hoy; para otro rango de fechas usa Reportes.",
      "Si algo se ve raro en un total del Dashboard, revisa que no haya una orden con datos incompletos en Órdenes."
    ],
    "/pos": [
      "En el Punto de Venta puedes buscar un producto por nombre o código en la casilla de arriba antes de agregarlo.",
      "Si el cliente paga combinando efectivo y tarjeta, puedes dividir el pago al finalizar la venta.",
      "El botón \"Finalizar venta\" solo se activa cuando el monto recibido cubre el total.",
      "Puedes vender sin seleccionar cliente (\"Cliente general\") si es una venta rápida de mostrador.",
      "Revisa el cambio antes de entregarlo: el sistema lo calcula solo con el monto recibido."
    ],
    "/ordenes/nueva": [
      "Antes de guardar, revisa que el IMEI o número de serie esté bien escrito: sirve para identificar el equipo después.",
      "Puedes anotar el PIN o patrón del equipo si el cliente lo autoriza; no aparece impreso en el recibo salvo que lo actives.",
      "Marca bien la condición física al recibir: es la mejor prueba si después el cliente reclama un daño que ya traía.",
      "Si el equipo ya trae un repuesto claro que vas a usar, agrégalo aquí mismo y se suma al total de una vez.",
      "¿No aparece la marca o el modelo? Puedes escribirlo manual, o agregarlo en Catálogo para la próxima vez."
    ],
    "/ordenes": [
      "Puedes filtrar las órdenes por estado desde los botones de arriba, o buscar por número de orden, cliente o IMEI.",
      "El filtro \"Vencidas\" te muestra solo las órdenes activas que llevan más días de la cuenta sin entregarse.",
      "Si un cliente pregunta por su equipo, busca por su nombre o teléfono, no hace falta el número de orden."
    ],
    "/clientes": [
      "Busca primero si el cliente ya existe antes de crear uno nuevo, así evitas duplicados.",
      "Entre más completo el teléfono/WhatsApp del cliente, más fácil avisarle cuando su equipo esté listo."
    ],
    "/inventario": [
      "Los productos con existencia igual o menor al mínimo configurado aparecen marcados como stock bajo.",
      "Cada movimiento de inventario queda en el historial del producto: entradas, salidas y ajustes, con quién lo hizo."
    ],
    "/facturas": [
      "Una factura fiscal solo se puede emitir si hay rango de CAI disponible; si no aparece la opción, avísale a un administrador.",
      "Una factura interna se puede anular si hay un error; una fiscal solo la puede anular un administrador."
    ],
    "/catalogo": [
      "Aquí se administran las marcas y modelos que luego aparecen como opciones al crear una orden nueva."
    ],
    "/reportes": [
      "Los reportes se pueden filtrar por fecha para ver solo un día, una semana o el rango que necesites.",
      "El reporte de saldos te muestra de un vistazo qué órdenes todavía deben dinero."
    ]
  };

  var ASISTENTE_SOLUCIONES = [
    "¿Un cliente no aparece en la búsqueda? Puede estar desactivado; pídele a un administrador que lo revise en Clientes.",
    "¿No se genera la factura fiscal? Es posible que se haya agotado el rango de CAI autorizado; un administrador puede actualizarlo en Configuración.",
    "¿Un producto no aparece en el Punto de Venta? Revisa que esté activo y con existencia disponible en Inventario.",
    "¿Te equivocaste de estado en una orden? Puedes corregirlo desde el detalle de la orden; el sistema guarda el historial de cada cambio.",
    "¿No encuentras una orden? Prueba buscar por el IMEI o el número de serie, no solo por el nombre del cliente.",
    "¿La sesión se cerró sola? Por seguridad se cierra tras un tiempo sin actividad; solo inicia sesión de nuevo.",
    "¿Agregaste un repuesto por error a una orden? Desde el detalle de la orden puedes quitarlo y se repone solo al inventario (si todavía no tiene factura).",
    "¿El cliente ya pagó todo y solo falta entregar? Al marcar la orden como ENTREGADO el sistema registra el pago pendiente automáticamente.",
    "¿No cuadra un total? Revisa que el recargo (%) y los repuestos de la orden estén correctos; el total se recalcula solo.",
    "¿Necesitas reimprimir un recibo? Desde Facturas puedes volver a abrir el PDF o la tirilla de cualquier factura ya generada."
  ];

  var ASISTENTE_MOTIVACION = [
    "Un cliente bien atendido siempre vuelve (y trae a otro).",
    "Revisa dos veces el IMEI o número de serie: ahorra dolores de cabeza después.",
    "Explicarle al cliente qué se le va a hacer al equipo, en corto, evita reclamos luego.",
    "Un dato de contacto correcto (teléfono/WhatsApp) vale oro cuando el equipo ya está listo.",
    "Cuenta el efectivo antes de guardarlo, sin prisa; es lo que más dolores de cabeza evita.",
    "¡Vas bien! Cualquier duda, pregúntale a un administrador."
  ];

  var resumenPanda = null; // se llena con /api/panda/resumen

  function consultarResumenPanda() {
    fetch("/api/panda/resumen")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        resumenPanda = data;
      })
      .catch(function () { /* sin conexión momentánea: el panda sigue funcionando sin el aviso */ });
  }

  function mensajeVencidas() {
    if (!resumenPanda || !resumenPanda.vencidas_total) return null;
    var detalle = resumenPanda.vencidas_detalle || [];
    var listado = detalle.slice(0, 3).map(function (o) { return o.numero_orden + " (" + o.dias + " días)"; }).join(", ");
    var n = resumenPanda.vencidas_total;
    return {
      texto: "Tienes " + n + " " + (n === 1 ? "orden activa" : "órdenes activas") +
        " que ya lleva" + (n === 1 ? "" : "n") + " " + resumenPanda.umbral_dias + " días o más sin entregarse" +
        (listado ? ": " + listado : "") + ".",
      alerta: true
    };
  }

  // ---------- Globo del asistente (se crea una sola vez, se reutiliza para
  // el consejo de presión larga Y para los avisos espontáneos/reacciones) ----------

  var globo = document.createElement("div");
  globo.className = "panda-asistente";
  globo.innerHTML =
    '<div class="panda-asistente-header">' +
    '<span>🐼 Asistente</span>' +
    '<span class="panda-asistente-cerrar" title="Cerrar">✕</span>' +
    '</div>' +
    '<div class="panda-asistente-msg"></div>' +
    '<div class="panda-asistente-pie">Mantén presionado al panda para otro consejo.</div>';
  document.body.appendChild(globo);
  var globoMsg = globo.querySelector(".panda-asistente-msg");
  var globoPie = globo.querySelector(".panda-asistente-pie");
  globo.querySelector(".panda-asistente-cerrar").addEventListener("click", cerrarAsistente);
  var globoAutoCerrarTimer = null;

  function posicionarJuntoAlPanda(el) {
    var tam = panda.getBoundingClientRect();
    // se mide oculto (no con display:none, que da 0x0) para saber su
    // tamaño real antes de decidir de qué lado del panda ponerlo
    el.style.visibility = "hidden";
    el.style.display = "block";
    var elAncho = el.offsetWidth || 260;
    var elAlto = el.offsetHeight || 80;
    el.style.display = "";
    el.style.visibility = "";

    var centroX = tam.left + tam.width / 2;
    var arriba = (tam.top + tam.height / 2) > window.innerHeight / 2;
    var izquierda = centroX > window.innerWidth / 2;

    var x = izquierda ? tam.left - elAncho - 10 : tam.right + 10;
    x = Math.max(8, Math.min(x, window.innerWidth - elAncho - 8));
    var y = arriba ? tam.top - elAlto - 8 : tam.bottom + 8;
    y = Math.max(8, Math.min(y, window.innerHeight - elAlto - 8));

    el.style.left = x + "px";
    el.style.top = y + "px";
  }

  // Muestra el globo con un mensaje. opts.autoCerrar: ms para cerrarlo solo
  // (null = se queda abierto hasta que lo cierren o toquen afuera, como el
  // consejo de presión larga). opts.pie: texto del pie; si no se manda, se
  // usa el de siempre.
  function mostrarGlobo(msj, opts) {
    opts = opts || {};
    clearTimeout(globoAutoCerrarTimer);
    globoMsg.textContent = msj.texto;
    globoMsg.classList.toggle("es-alerta", !!msj.alerta);
    globoPie.style.display = opts.pie === false ? "none" : "";
    if (opts.pie && typeof opts.pie === "string") globoPie.textContent = opts.pie;
    posicionarJuntoAlPanda(globo);
    globo.classList.add("mostrar");
    if (opts.autoCerrar) {
      globoAutoCerrarTimer = setTimeout(cerrarAsistente, opts.autoCerrar);
    }
  }

  function cerrarAsistente() {
    clearTimeout(globoAutoCerrarTimer);
    globo.classList.remove("mostrar");
  }

  document.addEventListener("click", function (e) {
    if (globo.classList.contains("mostrar") && !globo.contains(e.target) && !panda.contains(e.target)) {
      cerrarAsistente();
    }
  });

  // Reacciona (animación al azar) + muestra un mensaje que se cierra solo:
  // para eventos reales (pago, orden creada, factura, etc.), no para el
  // consejo de presión larga.
  function reaccionarConMensaje(texto, opts) {
    opts = opts || {};
    dispararReaccionAleatoria();
    mostrarGlobo({ texto: texto, alerta: !!opts.alerta }, { autoCerrar: opts.autoCerrar || 6000, pie: false });
  }
  window.pandaReaccionEvento = function (tipo, detalle) {
    if (tipo === "venta") {
      reaccionarConMensaje("¡Venta " + (detalle || "") + " registrada! 🎉", {});
    }
  };

  var ultimoMensaje = null;

  function elegirMensaje() {
    var pool = [];
    var msjVencidas = mensajeVencidas();
    // se agrega dos veces para que no quede opacada entre tantos tips
    if (msjVencidas) pool.push(msjVencidas, msjVencidas);

    var pagina = panda.dataset.pagina || "/";
    var tipsPagina = ASISTENTE_TIPS[pagina] || [];
    tipsPagina.forEach(function (t) { pool.push({ texto: t, alerta: false }); });
    ASISTENTE_SOLUCIONES.forEach(function (t) { pool.push({ texto: t, alerta: false }); });
    ASISTENTE_MOTIVACION.forEach(function (t) { pool.push({ texto: t, alerta: false }); });

    if (!pool.length) {
      pool.push({ texto: "¡Sigue así! Cualquier duda, pregúntale a un administrador.", alerta: false });
    }

    var elegido = pool[Math.floor(Math.random() * pool.length)];
    if (pool.length > 1 && ultimoMensaje && elegido.texto === ultimoMensaje.texto) {
      elegido = pool[Math.floor(Math.random() * pool.length)];
    }
    ultimoMensaje = elegido;
    return elegido;
  }

  function abrirAsistente() {
    mostrarGlobo(elegirMensaje(), { autoCerrar: null });
  }

  // ---------- Aparece solo de vez en cuando (vencidas, saludo del día, o un
  // consejo), sin quedarse fijo en pantalla como antes ----------

  function saludoRichardSiToca() {
    var hoy = new Date().toISOString().slice(0, 10);
    var ultimaFecha = null;
    try { ultimaFecha = localStorage.getItem(CLAVE_SALUDO_RICHARD); } catch (e) { ultimaFecha = null; }
    if (ultimaFecha === hoy) return false;
    try { localStorage.setItem(CLAVE_SALUDO_RICHARD, hoy); } catch (e) { /* sin almacenamiento: se podría repetir, no pasa nada grave */ }
    reaccionarConMensaje("Richard te manda saludos 👋 ¡Que tengas un excelente día!", { autoCerrar: 7000 });
    return true;
  }

  function pensamientoEspontaneo() {
    // Prioridad: saludo del día (si toca) > vencidas > un consejo cualquiera,
    // y con probabilidad para que no se sienta como una alarma constante.
    var hoy = new Date().toISOString().slice(0, 10);
    var yaSaludoHoy = false;
    try { yaSaludoHoy = localStorage.getItem(CLAVE_SALUDO_RICHARD) === hoy; } catch (e) { yaSaludoHoy = false; }

    if (!yaSaludoHoy && Math.random() < 0.4) {
      saludoRichardSiToca();
      return;
    }
    var msjVencidas = mensajeVencidas();
    if (msjVencidas && Math.random() < 0.6) {
      reaccionarConMensaje(msjVencidas.texto, { alerta: true, autoCerrar: 8000 });
      return;
    }
    if (Math.random() < 0.3) {
      var pagina = panda.dataset.pagina || "/";
      var pool = (ASISTENTE_TIPS[pagina] || []).concat(ASISTENTE_MOTIVACION);
      if (pool.length) {
        reaccionarConMensaje(pool[Math.floor(Math.random() * pool.length)], { autoCerrar: 7000 });
      }
    }
    // si no tocó nada de lo anterior, no aparece: justo lo que se pidió, que
    // no esté siempre encima avisando algo.
  }

  function programarPensamientoEspontaneo() {
    var demora = 20000 + Math.random() * 35000; // entre 20 y 55 segundos
    setTimeout(function () {
      // espera a tener el resumen de vencidas cargado antes de decidir
      if (resumenPanda === null) {
        setTimeout(pensamientoEspontaneo, 1500);
      } else {
        pensamientoEspontaneo();
      }
    }, demora);
  }

  // ---------- Reacciona a eventos reales: pago, orden creada, factura ----------
  // Lee los mensajes flash que el propio servidor ya deja tras la acción
  // (no inventa nada nuevo), y en vez de solo reaccionar al azar sin
  // motivo, lo hace justo cuando pasó algo que vale la pena celebrar.

  function revisarFlashesParaReaccion() {
    var flashes = document.querySelectorAll(".content .flash.flash-success");
    if (!flashes.length) return;
    var texto = Array.prototype.map.call(flashes, function (f) { return f.textContent || ""; }).join(" | ");

    if (/pago automático/i.test(texto)) {
      reaccionarConMensaje("¡Orden entregada y saldada! Buen trabajo. 💚", {});
    } else if (/factura[^|]*generada correctamente/i.test(texto)) {
      reaccionarConMensaje("¡Factura generada! 🧾", {});
    } else if (/abono de[^|]*registrado correctamente/i.test(texto)) {
      reaccionarConMensaje("¡Pago registrado! 💰", {});
    } else if (/orden[^|]*creada correctamente/i.test(texto)) {
      reaccionarConMensaje("¡Nueva orden registrada! 💪", {});
    }
  }

  // ---------- Info del cliente al seleccionarlo (Nueva Orden / POS) ----------

  function mostrarInfoCliente(clienteId) {
    if (!clienteId) return;
    fetch("/api/panda/cliente/" + encodeURIComponent(clienteId))
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.encontrado) return;
        var partes = [data.nombre];
        if (data.telefono) partes.push(data.telefono);
        var texto = "🧾 " + partes.join(" · ") + ". " +
          (data.ordenes_total > 0
            ? "Tiene " + data.ordenes_total + (data.ordenes_total === 1 ? " orden registrada" : " órdenes registradas") + "."
            : "Es su primera orden con nosotros.");
        if (data.saldo_pendiente > 0) {
          texto += " Debe L " + data.saldo_pendiente.toFixed(2) + " pendiente de otra orden.";
        }
        mostrarGlobo({ texto: texto, alerta: data.saldo_pendiente > 0 }, { autoCerrar: 7000, pie: false });
      })
      .catch(function () { /* sin conexión momentánea: no pasa nada, simplemente no se muestra */ });
  }

  document.addEventListener("change", function (e) {
    if (e.target && (e.target.id === "selectClienteId" || e.target.id === "posCliente") && e.target.value) {
      mostrarInfoCliente(e.target.value);
    }
  });

  // ---------- Autorelleno 1: aviso de cliente parecido al crear uno rápido ----------

  var temporizadorDuplicado = null;
  document.addEventListener("input", function (e) {
    if (!e.target || e.target.id !== "clienteRapidoNombre") return;
    clearTimeout(temporizadorDuplicado);
    var q = e.target.value.trim();
    if (q.length < 3) return;
    temporizadorDuplicado = setTimeout(function () {
      fetch("/api/buscar?q=" + encodeURIComponent(q))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.clientes || !data.clientes.length) return;
          var c = data.clientes[0];
          mostrarGlobo({
            texto: "Ya existe un cliente parecido: " + c.nombre + (c.telefono ? " · " + c.telefono : "") +
              ". Si es él, mejor cierra esto y selecciónalo de la lista en vez de crear uno nuevo.",
            alerta: false
          }, { autoCerrar: 8000, pie: false });
        })
        .catch(function () { /* sin conexión momentánea */ });
    }, 450);
  });

  // ---------- Autorelleno 2: frases frecuentes al describir la falla ----------

  var frasesFrecuentes = null;
  var cajaSugerencias = document.createElement("div");
  cajaSugerencias.className = "panda-sugerencias";
  document.body.appendChild(cajaSugerencias);

  function ocultarSugerenciasFrases() {
    cajaSugerencias.classList.remove("mostrar");
    cajaSugerencias.innerHTML = "";
  }

  function mostrarSugerenciasFrases(campo) {
    if (!frasesFrecuentes || !frasesFrecuentes.length) return;
    cajaSugerencias.innerHTML = '<div class="panda-sugerencias-titulo">Frases usadas antes (clic para usar):</div>';
    frasesFrecuentes.forEach(function (frase) {
      var item = document.createElement("div");
      item.className = "panda-sugerencias-item";
      item.textContent = frase;
      item.addEventListener("mousedown", function (e) {
        e.preventDefault();
        campo.value = campo.value.trim() ? campo.value.replace(/\.?\s*$/, "") + ". " + frase : frase;
        ocultarSugerenciasFrases();
      });
      cajaSugerencias.appendChild(item);
    });
    var rect = campo.getBoundingClientRect();
    cajaSugerencias.style.left = rect.left + "px";
    cajaSugerencias.style.top = (rect.bottom + 4) + "px";
    cajaSugerencias.style.width = Math.min(rect.width, 360) + "px";
    cajaSugerencias.classList.add("mostrar");
  }

  document.addEventListener("focus", function (e) {
    if (!e.target || !e.target.matches || !e.target.matches('textarea[name="falla_reportada"]')) return;
    var campo = e.target;
    if (frasesFrecuentes === null) {
      fetch("/api/panda/frases-frecuentes")
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          frasesFrecuentes = (data && data.frases) || [];
          mostrarSugerenciasFrases(campo);
        })
        .catch(function () { frasesFrecuentes = []; });
    } else {
      mostrarSugerenciasFrases(campo);
    }
  }, true);

  document.addEventListener("blur", function (e) {
    if (!e.target || !e.target.matches || !e.target.matches('textarea[name="falla_reportada"]')) return;
    setTimeout(ocultarSugerenciasFrases, 150);
  }, true);

  // ---------- Corrección 1: vender un repuesto por debajo de su costo ----------

  document.addEventListener("focusout", function (e) {
    if (!e.target || !e.target.matches ||
        !e.target.matches(".repuesto-input-precio, #inputRepuestoPrecio, #facturaRepuestoPrecio")) return;
    var fila = e.target.closest(".repuesto-fila") || e.target.closest("form");
    if (!fila) return;
    var select = fila.querySelector('select[name="repuesto_producto_id"], select[name="producto_id"]');
    if (!select || !select.value) return;
    var opcion = select.options[select.selectedIndex];
    var costo = opcion ? parseFloat(opcion.getAttribute("data-costo")) : NaN;
    var precio = parseFloat(e.target.value);
    if (costo > 0 && precio > 0 && precio < costo) {
      mostrarGlobo({
        texto: "⚠ Ese precio (L " + precio.toFixed(2) + ") queda por debajo del costo del producto (L " + costo.toFixed(2) + "). Vas a vender con pérdida.",
        alerta: true
      }, { autoCerrar: 9000, pie: false });
    }
  }, true);

  // ---------- Corrección 2: no dejar sin marcar la condición física ----------

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || !form.querySelector) return;
    var grid = form.querySelector("#condicionGrid");
    if (!grid) return;
    var marcado = grid.querySelector('input[type="checkbox"]:checked');
    if (!marcado) {
      e.preventDefault();
      mostrarGlobo({
        texto: "Falta marcar al menos un estado en \"Condición física al recibir\" antes de guardar (es obligatorio).",
        alerta: true
      }, { autoCerrar: null });
      grid.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, true);

  // ---------- Corrección 3: confirmar forma de pago si no es efectivo ----------

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form || form.getAttribute("action") === null) return;
    if (!/\/ordenes\/\d+\/abono$/.test(form.getAttribute("action") || "")) return;
    var selectFp = form.querySelector('select[name="forma_pago"]');
    var inputMonto = form.querySelector('input[name="monto"]');
    if (selectFp && selectFp.value !== "Efectivo") {
      var ok = confirm("Vas a registrar un abono de L " + (inputMonto ? inputMonto.value : "") + " vía " + selectFp.value + ". ¿Confirmas que es correcto?");
      if (!ok) e.preventDefault();
    }
  }, true);

  // ---------- Arrastrar + click corto (reacción) + presión larga (asistente) ----------

  function limitarYAplicar(x, y) {
    // panda es un <svg> inline: a diferencia de un <img>, no tiene
    // offsetWidth/offsetHeight (son API de HTMLElement, no de SVGElement),
    // así que el tamaño se lee con getBoundingClientRect().
    var tam = panda.getBoundingClientRect();
    var maxX = window.innerWidth - tam.width - 4;
    var maxY = window.innerHeight - tam.height - 4;
    x = Math.max(4, Math.min(x, maxX));
    y = Math.max(4, Math.min(y, maxY));
    panda.style.left = x + "px";
    panda.style.top = y + "px";
    panda.style.right = "auto";
    panda.style.bottom = "auto";
    if (globo.classList.contains("mostrar")) posicionarJuntoAlPanda(globo);
  }

  var posGuardada = null;
  try {
    posGuardada = JSON.parse(localStorage.getItem(CLAVE_POSICION) || "null");
  } catch (e) {
    posGuardada = null;
  }
  if (posGuardada && typeof posGuardada.x === "number" && typeof posGuardada.y === "number") {
    limitarYAplicar(posGuardada.x, posGuardada.y);
  }

  var arrastrando = false;
  var offsetX = 0, offsetY = 0;
  var inicioX = 0, inicioY = 0;
  var seArrastro = false;
  var temporizadorPresion = null;
  var presionLargaDisparada = false;

  function iniciarArrastre(clientX, clientY) {
    arrastrando = true;
    seArrastro = false;
    presionLargaDisparada = false;
    inicioX = clientX;
    inicioY = clientY;
    var rect = panda.getBoundingClientRect();
    offsetX = clientX - rect.left;
    offsetY = clientY - rect.top;
    panda.classList.add("panda-arrastrando");

    clearTimeout(temporizadorPresion);
    temporizadorPresion = setTimeout(function () {
      if (arrastrando && !seArrastro) {
        presionLargaDisparada = true;
        abrirAsistente();
      }
    }, UMBRAL_PRESION_LARGA);
  }

  function moverA(clientX, clientY) {
    if (!arrastrando) return;
    if (!seArrastro && Math.hypot(clientX - inicioX, clientY - inicioY) > UMBRAL_ARRASTRE) {
      seArrastro = true;
      clearTimeout(temporizadorPresion);
    }
    limitarYAplicar(clientX - offsetX, clientY - offsetY);
  }

  function soltar() {
    if (!arrastrando) return;
    arrastrando = false;
    clearTimeout(temporizadorPresion);
    panda.classList.remove("panda-arrastrando");
    if (seArrastro) {
      var rect = panda.getBoundingClientRect();
      try {
        localStorage.setItem(CLAVE_POSICION, JSON.stringify({ x: rect.left, y: rect.top }));
      } catch (e) {
        /* almacenamiento no disponible: simplemente no se recuerda la posición */
      }
    } else if (!presionLargaDisparada) {
      // Fue un toque/clic corto, no un arrastre ni una presión larga: reacciona.
      dispararReaccionAleatoria();
    }
    presionLargaDisparada = false;
  }

  panda.addEventListener("mousedown", function (e) {
    e.preventDefault();
    iniciarArrastre(e.clientX, e.clientY);
  });
  document.addEventListener("mousemove", function (e) { moverA(e.clientX, e.clientY); });
  document.addEventListener("mouseup", soltar);

  panda.addEventListener("touchstart", function (e) {
    var t = e.touches[0];
    iniciarArrastre(t.clientX, t.clientY);
  }, { passive: true });
  document.addEventListener("touchmove", function (e) {
    if (!arrastrando) return;
    var t = e.touches[0];
    moverA(t.clientX, t.clientY);
  }, { passive: true });
  document.addEventListener("touchend", soltar);

  // Si la ventana cambia de tamaño y la deja fuera de la pantalla, la
  // reacomoda dentro del área visible.
  window.addEventListener("resize", function () {
    var rect = panda.getBoundingClientRect();
    limitarYAplicar(rect.left, rect.top);
  });

  consultarResumenPanda();
  revisarFlashesParaReaccion();
  programarPensamientoEspontaneo();
}

document.addEventListener("DOMContentLoaded", function () {
  inicializarPandaMascota();
});
