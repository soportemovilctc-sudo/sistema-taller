"""«Ver en pantalla»: cualquier documento PDF del sistema se puede ver como
página web dentro del sistema (para quien no puede abrir PDF), sin quitar
los botones de PDF.

Basta agregar ?pantalla=1 a la dirección de un PDF (filtro de plantilla
`pantalla`). Este middleware deja que la ruta genere su PDF de siempre y,
en vez de mandarlo, lo convierte en imágenes (pypdfium2) y lo muestra en
una página con botones de Volver, Imprimir, Abrir PDF y Descargar PDF. Así
la vista es idéntica al PDF y no hay que mantener dos diseños por
documento."""
import base64
import html
import io
import re
from urllib.parse import parse_qsl, urlencode

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse

PARAM = "pantalla"
MAX_PAGINAS = 40
ESCALA = 2.0  # 144 ppp: nítido en pantalla y al imprimir


def url_pantalla(url: str) -> str:
    """Filtro de plantilla: la misma dirección del PDF con ?pantalla=1."""
    url = str(url or "")
    return url + ("&" if "?" in url else "?") + f"{PARAM}=1"


def _sin_param(path: str, query: str, extra: dict | None = None) -> str:
    pares = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k not in (PARAM, "descargar")]
    pares += list((extra or {}).items())
    return path + (("?" + urlencode(pares)) if pares else "")


def _nombre_archivo(disposition: str) -> str:
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition or "")
    return m.group(1) if m else "documento.pdf"


def _paginas_png(datos: bytes) -> list[tuple[float, float, str]]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(datos)
    try:
        paginas = []
        for i in range(min(len(pdf), MAX_PAGINAS)):
            page = pdf[i]
            ancho, alto = page.get_size()
            imagen = page.render(scale=ESCALA).to_pil()
            buf = io.BytesIO()
            imagen.convert("RGB").save(buf, format="PNG", optimize=True)
            paginas.append((ancho, alto, base64.b64encode(buf.getvalue()).decode("ascii")))
            page.close()
        return paginas
    finally:
        pdf.close()


def pagina_html(paginas, titulo: str, url_pdf: str, url_descarga: str, nombre: str, total_paginas: int | None = None) -> str:
    t = html.escape(titulo)
    w0, h0 = (paginas[0][0], paginas[0][1]) if paginas else (612, 792)
    if paginas:
        cuerpo = "\n".join(
            f'<img class="pg" alt="Página {i + 1}" style="width:{w:.1f}pt; max-width:100%;" src="data:image/png;base64,{b}">'
            for i, (w, h, b) in enumerate(paginas))
    else:
        cuerpo = f'<iframe class="pg" src="{html.escape(url_pdf)}" style="width:100%; height:85vh; border:0;"></iframe>'
    aviso = ""
    if total_paginas and total_paginas > len(paginas):
        aviso = f'<p class="aviso">Se muestran las primeras {len(paginas)} de {total_paginas} páginas. Descarga el PDF para verlo completo.</p>'
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; background: #e9ecf1; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #1d2433; }}
  .barra {{ position: sticky; top: 0; z-index: 2; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 10px 16px;
           background: #fff; border-bottom: 1px solid #d5dae3; box-shadow: 0 1px 4px rgba(0,0,0,.06); }}
  .barra .t {{ font-weight: 700; margin-right: auto; font-size: 15px; overflow-wrap: anywhere; }}
  .barra a, .barra button {{ font: inherit; font-size: 14px; display: inline-flex; align-items: center; min-height: 36px; padding: 0 14px;
           border-radius: 8px; border: 1px solid #c9d0dc; background: #fff; color: #1d2433; text-decoration: none; cursor: pointer; }}
  .barra .p {{ background: #2563eb; border-color: #2563eb; color: #fff; }}
  .hojas {{ display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 16px; }}
  .pg {{ display: block; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.15); height: auto; }}
  .aviso {{ text-align: center; color: #6b7280; font-size: 14px; }}
  @page {{ size: {w0:.1f}pt {h0:.1f}pt; margin: 0; }}
  @media print {{
    body {{ background: #fff; }}
    .barra, .aviso {{ display: none !important; }}
    .hojas {{ padding: 0; gap: 0; display: block; }}
    .pg {{ box-shadow: none; max-width: none !important; page-break-after: always; break-after: page; margin: 0; }}
    .pg:last-child {{ page-break-after: auto; break-after: auto; }}
  }}
</style></head>
<body>
<div class="barra">
  <span class="t">{t}</span>
  <button type="button" onclick="if (history.length > 1) history.back(); else window.close();">← Volver</button>
  <button type="button" class="p" onclick="window.print()">Imprimir</button>
  <a href="{html.escape(url_pdf)}" target="_blank" rel="noopener">Abrir PDF</a>
  <a href="{html.escape(url_descarga)}" download="{html.escape(nombre)}">Descargar PDF</a>
</div>
{aviso}
<div class="hojas">
{cuerpo}
</div>
</body></html>"""


class PantallaPdfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method != "GET" or request.query_params.get(PARAM) != "1":
            return await call_next(request)
        response = await call_next(request)
        if not response.headers.get("content-type", "").startswith("application/pdf"):
            return response
        datos = b"".join([chunk async for chunk in response.body_iterator])
        nombre = _nombre_archivo(response.headers.get("content-disposition", ""))
        path, query = request.url.path, request.url.query
        url_pdf = _sin_param(path, query)
        # Algunas rutas descargan con /descargar al final y otras con ?descargar=1.
        url_descarga = _sin_param(path, query, {"descargar": "1"})
        titulo = re.sub(r"\.pdf$", "", nombre, flags=re.I).replace("_", " ")
        total = None
        try:
            paginas = await run_in_threadpool(_paginas_png, datos)
            try:
                import pypdfium2 as pdfium
                total = len(pdfium.PdfDocument(datos))
            except Exception:  # noqa: BLE001
                total = None
        except Exception:  # noqa: BLE001 - sin el convertidor se muestra el PDF incrustado
            paginas = []
        return HTMLResponse(pagina_html(paginas, titulo, url_pdf, url_descarga, nombre, total))
