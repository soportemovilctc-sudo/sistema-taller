"""Utilidades para el editor de texto enriquecido de "Condiciones de Servicio
y Retiro de Equipos" (Configuración): convierten el HTML que guarda el editor
(estilo Word: negrita, cursiva, subrayado, color, alineación) al marcado
restringido que entiende reportlab.platypus.Paragraph, para que se imprima
igual en los 4 documentos donde aparece (orden y factura, carta y tirilla).

También trae un saneador simple para el HTML antes de guardarlo (solo lo
edita un administrador, pero de todas formas se limpia por higiene) y un
conversor de textos antiguos (formato "Título: texto" por línea, usado antes
de que existiera este editor) a un HTML inicial razonable, para no perder
configuraciones ya guardadas.
"""
import re
from html.parser import HTMLParser
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

_ALIGN_CLASSES = {
    "ql-align-center": TA_CENTER,
    "ql-align-right": TA_RIGHT,
    "ql-align-justify": TA_JUSTIFY,
}
_ALIGN_ESTILOS = {"center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY, "left": TA_LEFT}

_TAGS_BLOQUE = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}
_TAGS_INLINE_ABRIR = {"b": "<b>", "strong": "<b>", "i": "<i>", "em": "<i>", "u": "<u>"}
_TAGS_INLINE_CERRAR = {"b": "</b>", "strong": "</b>", "i": "</i>", "em": "</i>", "u": "</u>"}


def _rgb_a_hex(valor: str):
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", valor)
    if not m:
        return None
    r, g, b = (max(0, min(255, int(x))) for x in m.groups())
    return f"#{r:02x}{g:02x}{b:02x}"


def _color_de_style(valor_style: str):
    m = re.search(r"color\s*:\s*([^;]+)", valor_style or "")
    if not m:
        return None
    color = m.group(1).strip()
    if color.startswith("#"):
        return color
    if color.startswith("rgb"):
        return _rgb_a_hex(color)
    return None


def _align_de_atributos(attrs):
    align = None
    clases = ""
    style = ""
    for nombre, valor in attrs:
        if nombre == "class" and valor:
            clases = valor
        elif nombre == "style" and valor:
            style = valor
    for clase, ta in _ALIGN_CLASSES.items():
        if clase in clases:
            align = ta
    m = re.search(r"text-align\s*:\s*(center|right|justify|left)", style)
    if m:
        align = _ALIGN_ESTILOS[m.group(1)]
    return align


class _ParserCondiciones(HTMLParser):
    """Recorre el HTML del editor y arma una lista de (markup_reportlab,
    alineacion) — un elemento por párrafo/línea/ítem de lista."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bloques = []
        self._buffer = []
        self._align_actual = TA_LEFT
        self._pila_font = []

    def _cerrar_bloque_actual(self):
        markup = "".join(self._buffer)
        texto_visible = re.sub(r"<[^>]+>", "", markup).strip()
        if texto_visible:
            self.bloques.append((markup.strip(), self._align_actual))
        self._buffer = []
        self._align_actual = TA_LEFT

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _TAGS_BLOQUE:
            align = _align_de_atributos(attrs)
            if align is not None:
                self._align_actual = align
            if tag == "li":
                self._buffer.append("• ")
        elif tag == "br":
            self._buffer.append("<br/>")
        elif tag in _TAGS_INLINE_ABRIR:
            self._buffer.append(_TAGS_INLINE_ABRIR[tag])
        elif tag in ("span", "font"):
            color = None
            for nombre, valor in attrs:
                if nombre == "style":
                    color = _color_de_style(valor)
                elif nombre == "color" and not color:
                    color = valor
            if color:
                self._buffer.append(f'<font color="{color}">')
                self._pila_font.append(True)
            else:
                self._pila_font.append(False)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _TAGS_BLOQUE:
            self._cerrar_bloque_actual()
        elif tag in _TAGS_INLINE_CERRAR:
            self._buffer.append(_TAGS_INLINE_CERRAR[tag])
        elif tag in ("span", "font"):
            if self._pila_font and self._pila_font.pop():
                self._buffer.append("</font>")

    def handle_data(self, data):
        if data:
            self._buffer.append(escape(data))

    def close(self):
        super().close()
        self._cerrar_bloque_actual()


def parece_html(texto: str) -> bool:
    return bool(texto) and bool(re.search(r"<\s*[a-zA-Z][^>]*>", texto))


def condiciones_a_bloques(texto_condiciones: str):
    """Devuelve [(markup_reportlab, alineacion_TA_*), ...] listo para armar
    un Paragraph por bloque. Si el texto guardado no es HTML (configuración
    guardada antes de que existiera el editor enriquecido), se interpreta
    con el formato heredado "Título: texto por línea"."""
    texto_condiciones = (texto_condiciones or "").strip()
    if not texto_condiciones:
        return []
    if not parece_html(texto_condiciones):
        from app.models import parse_condiciones_servicio
        bloques = []
        for titulo, texto in parse_condiciones_servicio(texto_condiciones):
            if titulo:
                bloques.append((f"<b>{escape(titulo)}</b> {escape(texto)}", TA_LEFT))
            else:
                bloques.append((escape(texto), TA_LEFT))
        return bloques
    parser = _ParserCondiciones()
    parser.feed(texto_condiciones)
    parser.close()
    return parser.bloques


def condiciones_a_html_editor(texto_condiciones: str) -> str:
    """Valor inicial para cargar en el editor: si ya es HTML (guardado desde
    el editor), se usa tal cual; si es texto del formato heredado, se
    convierte a HTML equivalente (título en negrita) para no perder lo que
    el taller ya tenía configurado."""
    texto_condiciones = (texto_condiciones or "").strip()
    if not texto_condiciones:
        return ""
    if parece_html(texto_condiciones):
        return texto_condiciones
    from app.models import parse_condiciones_servicio
    partes = []
    for titulo, texto in parse_condiciones_servicio(texto_condiciones):
        if titulo:
            partes.append(f"<p><strong>{escape(titulo)}</strong> {escape(texto)}</p>")
        else:
            partes.append(f"<p>{escape(texto)}</p>")
    return "".join(partes)


_TAG_SCRIPT_RE = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_ATTR_ON_RE = re.compile(r'\son\w+\s*=\s*(".*?"|\'.*?\'|[^\s>]+)', re.IGNORECASE)
_TAG_IFRAME_STYLE_RE = re.compile(r"<\s*/?\s*(iframe|object|embed|link|meta)\b[^>]*>", re.IGNORECASE)


def sanear_html_condiciones(html_texto: str) -> str:
    """Limpieza defensiva antes de guardar: quita <script>, atributos on*=
    y etiquetas que no tienen sentido en este contexto. No es un sanitizador
    HTML completo, pero alcanza: solo lo edita un administrador y el HTML
    resultante nunca se ejecuta como página (solo se convierte a PDF o se
    inserta vía innerHTML, que tampoco corre <script>)."""
    if not html_texto:
        return ""
    limpio = _TAG_SCRIPT_RE.sub("", html_texto)
    limpio = _ATTR_ON_RE.sub("", limpio)
    limpio = _TAG_IFRAME_STYLE_RE.sub("", limpio)
    return limpio.strip()
