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

// Autocompletado de cliente: convierte cualquier <select class="js-cliente-buscar">
// en un campo de texto con sugerencias en vivo (buscar por nombre o teléfono
// mientras se escribe), sin cambiar cómo se envía el formulario: el <select>
// original sigue existiendo (oculto) y es el que se manda con el nombre/valor
// de siempre (p. ej. cliente_id).
function normalizarTextoBusqueda(s) {
  return (s || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function inicializarBuscarCliente() {
  document.querySelectorAll("select.js-cliente-buscar").forEach(function (select) {
    if (select.dataset.buscarClienteListo) return;
    select.dataset.buscarClienteListo = "1";

    var wrap = document.createElement("div");
    wrap.className = "cliente-buscar-wrap";

    var input = document.createElement("input");
    input.type = "text";
    input.className = "cliente-buscar-input";
    input.setAttribute("autocomplete", "off");
    input.placeholder = select.getAttribute("data-placeholder") || "Escribe para buscar un cliente...";

    var lista = document.createElement("div");
    lista.className = "cliente-buscar-resultados";

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
      input.classList.remove("cliente-buscar-error");
    }

    function ocultarLista() {
      lista.classList.remove("show");
      lista.innerHTML = "";
    }

    function mostrarResultados(items) {
      if (!items.length) {
        lista.innerHTML = '<div class="cliente-buscar-vacio">Sin coincidencias</div>';
        lista.classList.add("show");
        return;
      }
      lista.innerHTML = "";
      items.slice(0, 30).forEach(function (op) {
        var item = document.createElement("div");
        item.className = "cliente-buscar-item";
        item.textContent = op.textContent;
        item.addEventListener("mousedown", function (e) {
          e.preventDefault();
          select.value = op.value;
          input.value = op.textContent;
          input.classList.remove("cliente-buscar-error");
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
        var primero = lista.querySelector(".cliente-buscar-item");
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
  });

  document.querySelectorAll("select.js-cliente-buscar[required]").forEach(function (select) {
    var form = select.closest("form");
    if (!form || form.dataset.validacionClienteLista) return;
    form.dataset.validacionClienteLista = "1";
    form.addEventListener("submit", function (e) {
      var faltantes = Array.prototype.slice.call(form.querySelectorAll("select.js-cliente-buscar[required]"))
        .filter(function (s) { return !s.value; });
      if (!faltantes.length) return;
      e.preventDefault();
      var wrapFaltante = faltantes[0].closest(".cliente-buscar-wrap");
      var inputFaltante = wrapFaltante ? wrapFaltante.querySelector(".cliente-buscar-input") : null;
      if (inputFaltante) {
        inputFaltante.classList.add("cliente-buscar-error");
        inputFaltante.focus();
      }
      alert("Selecciona un cliente de la lista antes de continuar.");
    });
  });
}

document.addEventListener("DOMContentLoaded", function () {
  inicializarBuscarCliente();
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
