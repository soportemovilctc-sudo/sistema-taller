"""Intérprete de intención del asistente conversacional (chat del panda).

Es deliberadamente simple: reglas de palabras clave sobre texto en
español, sin IA externa ni costo por consulta (igual de "hecho en casa"
que el resto del asistente, que ya usa datos reales del sistema en vez
de inventar respuestas). Reconoce un vocabulario acotado de acciones
(marcar entregado, marcar avisado, registrar abono) más un poco de
plática básica; cualquier otra cosa cae en "desconocido" y el router le
explica al usuario qué sabe hacer.

`interpretar_mensaje` no toca la base de datos: solo extrae la
intención y, si aplica, el número de orden y el monto mencionados. La
resolución contra la base de datos (existe la orden, en qué estado
está, etc.) la hace app/routers/asistente.py, que es quien decide si
hay o no una acción para confirmar.
"""
import re
import unicodedata

PATRON_ORDEN = re.compile(r'(?:\borden(?:\s+numero)?\b|\bos\b|#)\s*[-\s]?\s*0*([0-9]{1,6})\b')
PATRON_SOLO_NUMERO = re.compile(r'0*([0-9]{1,6})')

PATRONES_MONTO = [
    r'\bl\.?\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    r'\blps\.?\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    r'\blempiras?\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    r'\bde\s+([0-9]+(?:[.,][0-9]{1,2})?)',
    r'\bpor\s+([0-9]+(?:[.,][0-9]{1,2})?)',
    r'([0-9]+(?:[.,][0-9]{1,2})?)',
]


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _extraer_monto(texto: str):
    for patron in PATRONES_MONTO:
        m = re.search(patron, texto)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                continue
    return None


def interpretar_mensaje(mensaje: str) -> dict:
    """Devuelve un dict con al menos la clave "intencion":
    - "marcar_entregado" | "marcar_notificado" | "registrar_abono":
      puede traer "numero_orden" (str|None) y, para abono, "monto" (float|None).
    - "conversacion": trae "texto", una respuesta fija (saludo, gracias, etc.).
    - "desconocido": no se reconoció ninguna acción ni plática; puede traer
      "numero_orden" si de todos modos se detectó un número.
    """
    texto_original = (mensaje or "").strip()
    texto_norm = _sin_acentos(texto_original.lower())

    if not texto_norm:
        return {"intencion": "conversacion", "texto": "Dime qué necesitas, por ejemplo: \"marca la orden 45 como entregada\"."}

    m_orden = PATRON_ORDEN.search(texto_norm)
    numero_orden = None
    resto = texto_norm
    if m_orden:
        numero_orden = m_orden.group(1)
        resto = texto_norm[:m_orden.start()] + " " + texto_norm[m_orden.end():]
    else:
        m_solo = PATRON_SOLO_NUMERO.fullmatch(texto_norm.strip())
        if m_solo:
            numero_orden = m_solo.group(1)
            resto = ""

    if re.search(r'\bentreg', texto_norm):
        return {"intencion": "marcar_entregado", "numero_orden": numero_orden}

    if re.search(r'\bnotific|\bavis', texto_norm):
        return {"intencion": "marcar_notificado", "numero_orden": numero_orden}

    if re.search(r'\babon|\bpago\b|\bpague|\bcobr', texto_norm):
        return {"intencion": "registrar_abono", "numero_orden": numero_orden, "monto": _extraer_monto(resto)}

    if re.search(r'^(hola|buenas|buenos dias|buenas tardes|buenas noches|hey|ola)\b', texto_norm):
        return {
            "intencion": "conversacion",
            "texto": "¡Hola! Puedo ayudarte a marcar una orden como entregada, avisar al cliente que ya está lista, o registrar un abono. ¿Qué necesitas?",
        }

    if re.search(r'\bgracias\b', texto_norm):
        return {"intencion": "conversacion", "texto": "¡Con gusto! Aquí ando si necesitas algo más."}

    if re.search(r'como estas|como andas|que tal\b', texto_norm):
        return {"intencion": "conversacion", "texto": "¡Muy bien, listo para ayudarte! ¿Qué necesitas?"}

    return {"intencion": "desconocido", "numero_orden": numero_orden}
