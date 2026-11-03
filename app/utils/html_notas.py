"""Limpia el HTML que sale del editor de notas: solo deja el formato básico
(negrita, cursiva, subrayado, tachado, colores de letra y resaltado, títulos,
listas, saltos de línea). Todo lo demás (scripts, enlaces, imágenes, estilos
raros, atributos on*) se descarta. Solo usa la librería estándar."""
import re
from html import escape
from html.parser import HTMLParser

ETIQUETAS = {"b", "strong", "i", "em", "u", "s", "strike", "p", "div", "br", "ul", "ol", "li", "h2", "h3", "span", "font", "mark"}
VACIAS = {"br"}
_COLOR = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(,\s*(0|1|0?\.\d+)\s*)?\)|[a-zA-Z]{3,20})$")
_ESTILOS = {"color", "background-color", "font-weight", "font-style", "text-decoration", "text-decoration-line", "text-align"}
_VALOR_SIMPLE = re.compile(r"^[a-zA-Z\- ]{1,30}$")


def _estilo_limpio(style: str) -> str:
    partes = []
    for decl in (style or "").split(";"):
        if ":" not in decl:
            continue
        prop, val = decl.split(":", 1)
        prop, val = prop.strip().lower(), val.strip()
        if prop not in _ESTILOS or "url" in val.lower() or "expression" in val.lower():
            continue
        if prop in ("color", "background-color"):
            if not _COLOR.match(val):
                continue
        elif not _VALOR_SIMPLE.match(val):
            continue
        partes.append(f"{prop}: {val}")
    return "; ".join(partes)


class _Limpiador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.salida = []
        self.texto = []
        self.abiertas = []
        self.saltar = 0  # dentro de <script>/<style>

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.saltar += 1
            return
        if self.saltar:
            return
        if tag not in ETIQUETAS:
            return
        if tag == "font":  # execCommand("foreColor") puede dar <font color>
            color = dict(attrs).get("color", "")
            tag, attrs = "span", ([("style", f"color: {color}")] if color and _COLOR.match(color) else [])
        estilo = _estilo_limpio(dict(attrs).get("style", ""))
        attr = f' style="{escape(estilo)}"' if estilo else ""
        self.salida.append(f"<{tag}{attr}>")
        if tag in VACIAS:
            self.texto.append("\n")
        else:
            self.abiertas.append(tag)
        if tag in ("p", "div", "li", "h2", "h3"):
            self.texto.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            self.saltar = max(0, self.saltar - 1)
            return
        if self.saltar:
            return
        if tag == "font":
            tag = "span"
        if tag in self.abiertas:
            while self.abiertas:
                t = self.abiertas.pop()
                self.salida.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if self.saltar:
            return
        self.salida.append(escape(data))
        self.texto.append(data)


def limpiar_html_nota(html: str, max_largo: int = 60000) -> tuple[str, str]:
    """Devuelve (html_limpio, texto_plano)."""
    p = _Limpiador()
    p.feed((html or "")[:max_largo])
    p.close()
    while p.abiertas:
        p.salida.append(f"</{p.abiertas.pop()}>")
    texto = re.sub(r"\n{3,}", "\n\n", "".join(p.texto)).strip()
    limpio = "".join(p.salida).strip()
    if not texto:
        limpio = ""
    return limpio, texto
