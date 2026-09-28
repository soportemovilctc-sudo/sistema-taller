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
//   - toque MANTENIDO (sin arrastrar)    -> abre el globo del asistente
//   - arrastre                            -> mueve al panda (como antes)
//
// El asistente (ver ASISTENTE_TIPS / ASISTENTE_SOLUCIONES más abajo) da
// consejos de uso según la página en la que está la cajera (usa
// data-pagina, que base.html llena con request.url.path), soluciones a
// problemas comunes, y un aviso de cuántas órdenes activas ya llevan
// demasiados días sin entregarse (mismo criterio que ya usa el Dashboard y
// el filtro "Vencidas" de Órdenes: config.dias_vencido_alerta), consultado
// en /api/panda/resumen. Por ahora es contenido fijo que yo redacté, sin
// conexión a ningún modelo de IA.
function inicializarPandaMascota() {
  var panda = document.getElementById("pandaCajaMascota");
  if (!panda) return;

  var CLAVE_POSICION = "pandaCajaPos";
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

  // ---------- Asistente: consejos por página + soluciones + vencidas ----------

  var ASISTENTE_TIPS = {
    "/": [
      "Desde el Dashboard puedes ver de un vistazo cuántas órdenes están listas para entregar y cuáles llevan más días de la cuenta."
    ],
    "/pos": [
      "En el Punto de Venta puedes buscar un producto por nombre o código en la casilla de arriba antes de agregarlo.",
      "Si el cliente paga combinando efectivo y tarjeta, puedes dividir el pago al finalizar la venta."
    ],
    "/ordenes/nueva": [
      "Antes de guardar, revisa que el IMEI o número de serie esté bien escrito: sirve para identificar el equipo después.",
      "Puedes anotar el PIN o patrón del equipo si el cliente lo autoriza; no aparece impreso en el recibo salvo que lo actives."
    ],
    "/ordenes": [
      "Puedes filtrar las órdenes por estado desde los botones de arriba, o buscar por número de orden, cliente o IMEI.",
      "El filtro \"Vencidas\" te muestra solo las órdenes activas que llevan más días de la cuenta sin entregarse."
    ],
    "/clientes": [
      "Busca primero si el cliente ya existe antes de crear uno nuevo, así evitas duplicados."
    ],
    "/inventario": [
      "Los productos con existencia igual o menor al mínimo configurado aparecen marcados como stock bajo."
    ],
    "/facturas": [
      "Una factura fiscal solo se puede emitir si hay rango de CAI disponible; si no aparece la opción, avísale a un administrador."
    ],
    "/catalogo": [
      "Aquí se administran las marcas y modelos que luego aparecen como opciones al crear una orden nueva."
    ],
    "/reportes": [
      "Los reportes se pueden filtrar por fecha para ver solo un día, una semana o el rango que necesites."
    ]
  };

  var ASISTENTE_SOLUCIONES = [
    "¿Un cliente no aparece en la búsqueda? Puede estar desactivado; pídele a un administrador que lo revise en Clientes.",
    "¿No se genera la factura fiscal? Es posible que se haya agotado el rango de CAI autorizado; un administrador puede actualizarlo en Configuración.",
    "¿Un producto no aparece en el Punto de Venta? Revisa que esté activo y con existencia disponible en Inventario.",
    "¿Te equivocaste de estado en una orden? Puedes corregirlo desde el detalle de la orden; el sistema guarda el historial de cada cambio.",
    "¿No encuentras una orden? Prueba buscar por el IMEI o el número de serie, no solo por el nombre del cliente.",
    "¿La sesión se cerró sola? Por seguridad se cierra tras un tiempo sin actividad; solo inicia sesión de nuevo."
  ];

  var resumenPanda = null; // se llena con /api/panda/resumen

  function consultarResumenPanda() {
    fetch("/api/panda/resumen")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        resumenPanda = data;
        actualizarBadgePanda();
      })
      .catch(function () { /* sin conexión momentánea: el panda sigue funcionando sin el aviso */ });
  }

  // ---------- Elementos del badge y del globo (se crean una sola vez) ----------

  var badge = document.createElement("div");
  badge.className = "panda-badge";
  document.body.appendChild(badge);

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
  globo.querySelector(".panda-asistente-cerrar").addEventListener("click", cerrarAsistente);

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

  function actualizarBadgePanda() {
    if (!resumenPanda || !resumenPanda.vencidas_total) {
      badge.classList.remove("mostrar");
      return;
    }
    badge.textContent = resumenPanda.vencidas_total > 9 ? "9+" : String(resumenPanda.vencidas_total);
    var tam = panda.getBoundingClientRect();
    badge.style.left = (tam.right - 14) + "px";
    badge.style.top = (tam.top - 6) + "px";
    badge.classList.add("mostrar");
  }

  var ultimoMensaje = null;

  function elegirMensaje() {
    var pool = [];
    if (resumenPanda && resumenPanda.vencidas_total > 0) {
      var detalle = resumenPanda.vencidas_detalle || [];
      var listado = detalle.slice(0, 3).map(function (o) { return o.numero_orden + " (" + o.dias + " días)"; }).join(", ");
      var n = resumenPanda.vencidas_total;
      var msjVencidas = {
        texto: "Tienes " + n + " " + (n === 1 ? "orden activa" : "órdenes activas") +
          " que ya lleva" + (n === 1 ? "" : "n") + " " + resumenPanda.umbral_dias + " días o más sin entregarse" +
          (listado ? ": " + listado : "") + ".",
        alerta: true
      };
      // se agrega dos veces para que no quede opacada entre tantos tips
      pool.push(msjVencidas, msjVencidas);
    }
    var pagina = panda.dataset.pagina || "/";
    var tipsPagina = ASISTENTE_TIPS[pagina] || [];
    tipsPagina.forEach(function (t) { pool.push({ texto: t, alerta: false }); });
    ASISTENTE_SOLUCIONES.forEach(function (t) { pool.push({ texto: t, alerta: false }); });

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
    var msj = elegirMensaje();
    globoMsg.textContent = msj.texto;
    globoMsg.classList.toggle("es-alerta", !!msj.alerta);
    posicionarJuntoAlPanda(globo);
    globo.classList.add("mostrar");
  }

  function cerrarAsistente() {
    globo.classList.remove("mostrar");
  }

  document.addEventListener("click", function (e) {
    if (globo.classList.contains("mostrar") && !globo.contains(e.target) && !panda.contains(e.target)) {
      cerrarAsistente();
    }
  });

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
    actualizarBadgePanda();
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
}

document.addEventListener("DOMContentLoaded", function () {
  inicializarPandaMascota();
});
