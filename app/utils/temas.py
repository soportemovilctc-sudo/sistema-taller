"""Temas de Apariencia.

Cada usuario elige un tema (Usuario.tema_modo). Los temas «completos»
cambian fondo, tarjetas, menú, bordes y color principal a la vez, y se
montan sobre uno de los modos de siempre (oscuro/claro) para heredar todos
sus ajustes de legibilidad: base.html pone data-tema="<base>" y
data-variante="<tema>", y style.css cambia solo los colores.

«De temporada» cambia solo según la fecha de Honduras (Navidad, San
Valentín, Fiestas Patrias, Halloween); el resto del año usa el tema base
que eligió el usuario. Se guarda como "temporada:<base>"."""
from datetime import date

PREFIJO_TEMPORADA = "temporada"

# valor -> datos. base: modo sobre el que se monta. propio: trae su propio
# color (el acento elegido no se usa). prev: colores de la vista previa.
TEMAS = {
    "oscuro":     {"nombre": "Oscuro", "grupo": "Clásicos", "base": "oscuro", "propio": False,
                   "prev": ("#0e1116", "#12161c", "#161b22", "#2563eb", "#e6edf3")},
    "claro":      {"nombre": "Claro", "grupo": "Clásicos", "base": "claro", "propio": False,
                   "prev": ("#f6f7f9", "#eef0f3", "#ffffff", "#2563eb", "#111827")},
    "vidrio":     {"nombre": "Vidrio", "grupo": "Clásicos", "base": "vidrio", "propio": True,
                   "prev": ("#070b12", "#0b1420", "#13202e", "#22d3ee", "#eaf6fb")},
    "medianoche": {"nombre": "Medianoche", "grupo": "Oscuros", "base": "oscuro", "propio": True,
                   "prev": ("#000000", "#06060a", "#0d0d14", "#8b5cf6", "#ececf4")},
    "oceano":     {"nombre": "Océano", "grupo": "Oscuros", "base": "oscuro", "propio": True,
                   "prev": ("#06182a", "#081f36", "#0c2a47", "#14b8a6", "#e2f3f8")},
    "bosque":     {"nombre": "Bosque", "grupo": "Oscuros", "base": "oscuro", "propio": True,
                   "prev": ("#0b1510", "#0f1d16", "#14261c", "#34d399", "#e3f1e8")},
    "neon":       {"nombre": "Neón", "grupo": "Oscuros", "base": "oscuro", "propio": True,
                   "prev": ("#07060d", "#0c0a16", "#120f20", "#d946ef", "#f0eaff")},
    "arena":      {"nombre": "Arena", "grupo": "Claros", "base": "claro", "propio": True,
                   "prev": ("#f4efe6", "#ebe3d5", "#fbf8f2", "#b45309", "#3b2f22")},
    "grafito":    {"nombre": "Grafito", "grupo": "Claros", "base": "claro", "propio": True,
                   "prev": ("#eef0f2", "#e2e5e9", "#ffffff", "#1f2937", "#111418")},
    "atardecer":  {"nombre": "Atardecer", "grupo": "Claros", "base": "claro", "propio": True,
                   "prev": ("#fff4ee", "#ffe9df", "#ffffff", "#f43f5e", "#3a1d26")},
    "contraste":  {"nombre": "Alto contraste", "grupo": "Claros", "base": "claro", "propio": True,
                   "prev": ("#ffffff", "#ffffff", "#ffffff", "#000000", "#000000")},
}

# De temporada (no se eligen sueltos: los pone la fecha).
TEMPORADAS = {
    "navidad":     {"nombre": "Navidad", "base": "oscuro", "desde": (11, 1), "hasta": (1, 6),
                    "prev": ("#0d1a14", "#102219", "#162c21", "#dc2626", "#f6efe3")},
    "sanvalentin": {"nombre": "San Valentín", "base": "claro", "desde": (2, 1), "hasta": (2, 14),
                    "prev": ("#fff1f4", "#ffe4ea", "#ffffff", "#e11d48", "#3b0f1c")},
    "patrias":     {"nombre": "Fiestas Patrias", "base": "claro", "desde": (9, 1), "hasta": (9, 20),
                    "prev": ("#f1f8fc", "#e3f1f9", "#ffffff", "#0087c8", "#0b2a3d")},
    "halloween":   {"nombre": "Halloween", "base": "oscuro", "desde": (10, 15), "hasta": (10, 31),
                    "prev": ("#110b14", "#170f1b", "#1f1424", "#f97316", "#f6ece2")},
}

GRUPOS = ("Clásicos", "Oscuros", "Claros")


def _en_rango(hoy: date, desde, hasta) -> bool:
    d, h = (hoy.month, hoy.day), None
    if desde <= hasta:
        return desde <= d <= hasta
    return d >= desde or d <= hasta  # cruza el año (Navidad: nov → ene)


def temporada_de(hoy: date) -> str | None:
    for clave, t in TEMPORADAS.items():
        if _en_rango(hoy, t["desde"], t["hasta"]):
            return clave
    return None


def es_temporada(valor: str) -> bool:
    return (valor or "").split(":")[0] == PREFIJO_TEMPORADA


def base_de_temporada(valor: str) -> str:
    partes = (valor or "").split(":", 1)
    b = partes[1] if len(partes) > 1 else "oscuro"
    return b if b in TEMAS else "oscuro"


def valor_guardado(tema: str, base_temporada: str = "") -> str:
    """Del formulario a lo que se guarda en Usuario.tema_modo."""
    if tema == PREFIJO_TEMPORADA:
        return f"{PREFIJO_TEMPORADA}:{base_temporada if base_temporada in TEMAS else 'oscuro'}"
    return tema if tema in TEMAS else "oscuro"


def resolver(valor: str, hoy: date | None = None) -> dict:
    """Lo que base.html pone en <html>: data-tema (modo base), data-variante
    (el tema completo, vacío para Oscuro/Claro/Vidrio) y la temporada activa."""
    if hoy is None:
        from app.utils.turnos_caja import hoy_local
        hoy = hoy_local()
    temporada = None
    if es_temporada(valor):
        temporada = temporada_de(hoy)
        if temporada:
            t = TEMPORADAS[temporada]
            return {"tema": t["base"], "variante": temporada, "temporada": temporada, "propio": True, "nombre": t["nombre"]}
        valor = base_de_temporada(valor)
    t = TEMAS.get(valor) or TEMAS["oscuro"]
    clave = valor if valor in TEMAS else "oscuro"
    return {"tema": t["base"], "variante": clave if clave not in ("oscuro", "claro", "vidrio") else "",
            "temporada": None, "propio": t["propio"], "nombre": t["nombre"]}


def fechas_temporadas() -> list[dict]:
    meses = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return [{"clave": k, "nombre": t["nombre"], "prev": t["prev"],
             "fechas": f"{t['desde'][1]} {meses[t['desde'][0]]} – {t['hasta'][1]} {meses[t['hasta'][0]]}"}
            for k, t in TEMPORADAS.items()]
