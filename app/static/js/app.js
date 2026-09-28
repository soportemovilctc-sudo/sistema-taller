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
// sistema recarga toda la página en cada navegación, no es un SPA). Un
// toque/clic que NO arrastra (no se movió más que UMBRAL_ARRASTRE) dispara
// una reacción al azar entre varias (ver REACCIONES), usando el mecanismo
// nativo de SVG (begin="indefinite" + beginElement()) para reiniciar una
// animación puntual a demanda.
function inicializarPandaMascota() {
  var panda = document.getElementById("pandaCajaMascota");
  if (!panda) return;

  var CLAVE_POSICION = "pandaCajaPos";
  var UMBRAL_ARRASTRE = 6; // px de movimiento antes de considerarlo arrastre y no un toque

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

  function iniciarArrastre(clientX, clientY) {
    arrastrando = true;
    seArrastro = false;
    inicioX = clientX;
    inicioY = clientY;
    var rect = panda.getBoundingClientRect();
    offsetX = clientX - rect.left;
    offsetY = clientY - rect.top;
    panda.classList.add("panda-arrastrando");
  }

  function moverA(clientX, clientY) {
    if (!arrastrando) return;
    if (!seArrastro && Math.hypot(clientX - inicioX, clientY - inicioY) > UMBRAL_ARRASTRE) {
      seArrastro = true;
    }
    limitarYAplicar(clientX - offsetX, clientY - offsetY);
  }

  function soltar() {
    if (!arrastrando) return;
    arrastrando = false;
    panda.classList.remove("panda-arrastrando");
    if (seArrastro) {
      var rect = panda.getBoundingClientRect();
      try {
        localStorage.setItem(CLAVE_POSICION, JSON.stringify({ x: rect.left, y: rect.top }));
      } catch (e) {
        /* almacenamiento no disponible: simplemente no se recuerda la posición */
      }
    } else {
      // Fue un toque/clic, no un arrastre: reacciona.
      dispararReaccionAleatoria();
    }
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
}

document.addEventListener("DOMContentLoaded", function () {
  inicializarPandaMascota();
});
