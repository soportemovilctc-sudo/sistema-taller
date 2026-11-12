"""Ropero de la mascota.

Cada usuario combina 4 partes (cabeza, ojos, cuello, en la mano) y puede
dejar que la mascota se vista sola según la temporada (Navidad, Halloween,
San Valentín, Fiestas Patrias). En esas fechas el traje de temporada cambia
solo las partes que trae; las demás quedan como el usuario las eligió.

Se guarda en Usuario.mascota_ropa como "cabeza=gorra;ojos=sol;cuello=;mano=;temporada=1".
Vacío = solo el traje de temporada.

Las piezas son SVG dibujados alrededor de un punto (0,0) de su parte del
cuerpo; ANCLAS dice dónde queda ese punto (y a qué escala) en cada mascota.
Panda, león y ratón comparten el mismo esqueleto (viewBox -25 -45 290 330);
el robot es una imagen de 420x514."""
from datetime import date

PARTES = ("cabeza", "ojos", "cuello", "mano")
NOMBRE_PARTE = {"cabeza": "Cabeza", "ojos": "Ojos", "cuello": "Cuello", "mano": "En la mano"}
L = 'stroke="#1a1a1a" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"'
CORAZON = "M0,6 C-12,-4 -10,-14 -3,-14 C0,-14 0,-11 0,-10 C0,-11 0,-14 3,-14 C10,-14 12,-4 0,6 Z"

# (valor, nombre, svg). Coordenadas alrededor de (0,0) del ancla.
PIEZAS = {
    "cabeza": [
        ("gorra", "Gorra", f'<path d="M-54,12 Q-52,-46 0,-48 Q52,-46 54,12 Z" fill="#2563eb" {L}/><ellipse cx="44" cy="12" rx="40" ry="9" fill="#1d4ed8" {L}/><circle cx="0" cy="-47" r="5" fill="#1d4ed8" {L}/>'),
        ("vaquero", "Sombrero vaquero", f'<path d="M-88,8 Q-82,-8 -60,2 Q0,18 60,2 Q82,-8 88,8 Q60,26 0,24 Q-60,26 -88,8 Z" fill="#a16207" {L}/><path d="M-40,6 Q-44,-50 -16,-52 Q0,-40 16,-52 Q44,-50 40,6 Z" fill="#ca8a04" {L}/><path d="M-41,-8 L41,-8 L40,3 L-40,3 Z" fill="#78350f"/>'),
        ("corona", "Corona", f'<path d="M-46,10 L-52,-38 L-25,-14 L0,-48 L25,-14 L52,-38 L46,10 Z" fill="#facc15" {L}/><circle cx="0" cy="-6" r="6" fill="#dc2626" {L}/><circle cx="-28" cy="-2" r="4" fill="#2563eb"/><circle cx="28" cy="-2" r="4" fill="#16a34a"/>'),
        ("casco", "Casco de técnico", f'<path d="M-60,14 Q-58,-52 0,-54 Q58,-52 60,14 Z" fill="#facc15" {L}/><path d="M-7,-53 L7,-53 L7,12 L-7,12 Z" fill="#fde047" {L}/><rect x="-72" y="8" width="144" height="12" rx="6" fill="#eab308" {L}/>'),
        ("lana", "Gorro de lana", f'<path d="M-58,16 Q-56,-48 0,-50 Q56,-48 58,16 Z" fill="#0ea5e9" {L}/><rect x="-62" y="0" width="124" height="20" rx="8" fill="#0284c7" {L}/><circle cx="0" cy="-54" r="13" fill="#e0f2fe" {L}/>'),
        ("mono", "Moño", f'<g transform="translate(46,6) rotate(18)"><path d="M0,0 L-24,-14 L-24,14 Z" fill="#ec4899" {L}/><path d="M0,0 L24,-14 L24,14 Z" fill="#ec4899" {L}/><circle r="7" fill="#db2777" {L}/></g>'),
    ],
    "ojos": [
        ("sol", "Lentes de sol", f'<path d="M-62,-6 L-80,-12 M62,-6 L80,-12" {L} fill="none"/><rect x="-56" y="-18" width="52" height="36" rx="14" fill="#0f172a" fill-opacity=".92" {L}/><rect x="4" y="-18" width="52" height="36" rx="14" fill="#0f172a" fill-opacity=".92" {L}/><path d="M-4,-6 Q0,-11 4,-6" {L} fill="none"/><path d="M-46,-10 L-30,-10 M14,-10 L30,-10" stroke="#fff" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"/>'),
        ("nerd", "Lentes de nerd", f'<path d="M-54,-4 L-80,-12 M54,-4 L80,-12" {L} fill="none"/><circle cx="-29" cy="0" r="25" fill="#fff" fill-opacity=".12" stroke="#1a1a1a" stroke-width="6"/><circle cx="29" cy="0" r="25" fill="#fff" fill-opacity=".12" stroke="#1a1a1a" stroke-width="6"/><path d="M-5,-4 Q0,-10 5,-4" stroke="#1a1a1a" stroke-width="5" fill="none"/>'),
        ("lentes3d", "Lentes 3D", f'<rect x="-60" y="-20" width="120" height="40" rx="6" fill="#fff" {L}/><rect x="-52" y="-13" width="44" height="26" rx="4" fill="#ef4444" fill-opacity=".85"/><rect x="8" y="-13" width="44" height="26" rx="4" fill="#06b6d4" fill-opacity=".85"/>'),
        ("monoculo", "Monóculo", '<circle cx="29" cy="0" r="25" fill="#fff" fill-opacity=".14" stroke="#ca8a04" stroke-width="5"/><path d="M48,16 Q62,40 50,70" stroke="#ca8a04" stroke-width="2.5" fill="none" stroke-dasharray="4 3"/>'),
    ],
    "cuello": [
        ("bufanda", "Bufanda", f'<path d="M-64,-8 Q0,14 64,-8 L64,12 Q0,34 -64,12 Z" fill="#7c3aed" {L}/><path d="M26,14 L48,10 L52,62 L32,64 Z" fill="#7c3aed" {L}/><path d="M34,30 L50,28 M35,44 L51,42" stroke="#c4b5fd" stroke-width="4"/>'),
        ("corbatin", "Corbatín", f'<path d="M0,6 L-28,-9 L-28,21 Z" fill="#111827" {L}/><path d="M0,6 L28,-9 L28,21 Z" fill="#111827" {L}/><circle cx="0" cy="6" r="7" fill="#374151" {L}/>'),
        ("corbata", "Corbata", f'<path d="M-8,0 L8,0 L6,11 L-6,11 Z" fill="#1d4ed8" {L}/><path d="M-6,11 L6,11 L13,58 L0,72 L-13,58 Z" fill="#2563eb" {L}/><path d="M-9,30 L9,24 M-11,46 L11,40" stroke="#93c5fd" stroke-width="3"/>'),
        ("medalla", "Medalla de oro", f'<path d="M-30,-6 L0,34 L30,-6" stroke="#2563eb" stroke-width="9" fill="none" stroke-linejoin="round"/><circle cx="0" cy="44" r="15" fill="#facc15" {L}/><path d="M0,36 L3,42 L9,42 L4,46 L6,52 L0,48 L-6,52 L-4,46 L-9,42 L-3,42 Z" fill="#fef9c3"/>'),
        ("panuelo", "Pañuelo", f'<path d="M-54,-6 L54,-6 L0,42 Z" fill="#ef4444" {L}/><circle cx="-16" cy="6" r="3" fill="#fff"/><circle cx="16" cy="6" r="3" fill="#fff"/><circle cx="0" cy="22" r="3" fill="#fff"/>'),
    ],
    "mano": [
        ("destornillador", "Destornillador", f'<g transform="rotate(-35)"><rect x="-7" y="-4" width="14" height="30" rx="6" fill="#ef4444" {L}/><path d="M0,-4 L0,-42" stroke="#94a3b8" stroke-width="5" stroke-linecap="round"/><path d="M-4,-42 L4,-42" stroke="#64748b" stroke-width="4"/></g>'),
        ("cafe", "Taza de café", f'<path d="M-14,-22 L14,-22 L11,8 L-11,8 Z" fill="#fff" {L}/><path d="M13,-14 Q26,-12 12,0" fill="none" {L}/><path d="M-14,-16 L14,-16" stroke="#92400e" stroke-width="4"/><path d="M-5,-30 Q-9,-36 -4,-42 M5,-30 Q1,-36 6,-42" stroke="#94a3b8" stroke-width="2.5" fill="none" stroke-linecap="round"/>'),
        ("celular", "Celular", f'<rect x="-12" y="-30" width="24" height="42" rx="5" fill="#111827" {L}/><rect x="-8" y="-25" width="16" height="30" rx="2" fill="#38bdf8"/><circle cx="0" cy="8" r="1.8" fill="#9ca3af"/>'),
        ("lupa", "Lupa", f'<path d="M8,0 L22,16" stroke="#78350f" stroke-width="7" stroke-linecap="round"/><circle cx="-2" cy="-12" r="15" fill="#e0f2fe" fill-opacity=".55" stroke="#475569" stroke-width="5"/>'),
    ],
}

# Piezas que solo pone la temporada (no salen en el ropero).
PIEZAS_TEMPORADA = {
    "santa": f'<rect x="-64" y="-2" width="128" height="22" rx="11" fill="#fff" {L}/><path d="M-54,0 C-46,-56 8,-86 62,-60 C70,-56 74,-48 70,-42 C44,-52 22,-40 52,0 Z" fill="#dc2626" {L}/><circle cx="72" cy="-42" r="13" fill="#fff" {L}/>',
    "bufanda_navidad": f'<path d="M-64,-8 Q0,14 64,-8 L64,12 Q0,34 -64,12 Z" fill="#16a34a" {L}/><path d="M-40,2 L-40,22 M-14,6 L-14,26 M14,6 L14,26 M40,2 L40,22" stroke="#dc2626" stroke-width="7"/><path d="M26,14 L48,10 L52,62 L32,64 Z" fill="#16a34a" {L}/><path d="M33,30 L50,28 M34,46 L51,44" stroke="#dc2626" stroke-width="6"/>',
    "regalo": f'<rect x="-16" y="-26" width="32" height="30" rx="3" fill="#dc2626" {L}/><path d="M0,-26 L0,4 M-16,-12 L16,-12" stroke="#facc15" stroke-width="5"/><path d="M0,-26 Q-12,-40 -14,-28 Q-10,-24 0,-26 Q12,-40 14,-28 Q10,-24 0,-26 Z" fill="#facc15" {L}/>',
    "bruja": f'<ellipse cx="0" cy="6" rx="80" ry="13" fill="#2e1065" {L}/><path d="M-40,4 L-6,-82 Q2,-94 12,-78 Q4,-70 14,-62 L40,4 Z" fill="#3b0764" {L}/><path d="M-34,-12 L34,-12 L38,-2 L-38,-2 Z" fill="#f97316"/>',
    "cuello_capa": f'<path d="M-62,-8 L-22,4 L-50,30 Z" fill="#3b0764" {L}/><path d="M62,-8 L22,4 L50,30 Z" fill="#3b0764" {L}/><circle cx="0" cy="6" r="7" fill="#f97316" {L}/>',
    "calabaza": f'<ellipse cx="0" cy="-8" rx="20" ry="16" fill="#f97316" {L}/><path d="M-7,-22 Q0,-8 -7,6 M7,-22 Q0,-8 7,6" stroke="#c2410c" stroke-width="2" fill="none"/><path d="M0,-24 L3,-32" stroke="#166534" stroke-width="4" stroke-linecap="round"/><path d="M-9,-12 L-4,-14 L-6,-8 Z M9,-12 L4,-14 L6,-8 Z" fill="#1a1a1a"/>',
    "diadema_corazones": f'<path d="M-70,24 Q0,-22 70,24" stroke="#e11d48" stroke-width="6" fill="none" stroke-linecap="round"/><g transform="translate(-28,-6) scale(1.8)"><path d="{CORAZON}" fill="#f43f5e" stroke="#1a1a1a" stroke-width="1.6"/></g><g transform="translate(28,-6) scale(1.8)"><path d="{CORAZON}" fill="#f43f5e" stroke="#1a1a1a" stroke-width="1.6"/></g>',
    "collar_corazon": f'<path d="M-50,-6 Q0,26 50,-6" stroke="#fda4af" stroke-width="3" fill="none"/><g transform="translate(0,22) scale(1.5)"><path d="{CORAZON}" fill="#e11d48" stroke="#1a1a1a" stroke-width="1.8"/></g>',
    "globo_corazon": f'<path d="M0,0 Q-6,-20 0,-34" stroke="#64748b" stroke-width="2" fill="none"/><g transform="translate(0,-44) scale(2.2)"><path d="{CORAZON}" fill="#f43f5e" stroke="#1a1a1a" stroke-width="1.3"/></g>',
    "banda_patria": f'<path d="M-64,-10 Q0,12 64,-10 L64,14 Q0,36 -64,14 Z" fill="#18c3df" {L}/><path d="M-64,-2 Q0,20 64,-2 L64,6 Q0,28 -64,6 Z" fill="#fff"/>',
    "bandera": f'<path d="M0,10 L0,-56" stroke="#78350f" stroke-width="4" stroke-linecap="round"/><rect x="0" y="-56" width="44" height="30" fill="#fff" {L}/><rect x="1.5" y="-54.5" width="41" height="9" fill="#18c3df"/><rect x="1.5" y="-36.5" width="41" height="9" fill="#18c3df"/><g fill="#18c3df"><circle cx="22" cy="-41" r="1.6"/><circle cx="16" cy="-43" r="1.3"/><circle cx="28" cy="-43" r="1.3"/><circle cx="16" cy="-39" r="1.3"/><circle cx="28" cy="-39" r="1.3"/></g>',
}

TRAJES_TEMPORADA = {
    "navidad": {"cabeza": "santa", "cuello": "bufanda_navidad", "mano": "regalo"},
    "halloween": {"cabeza": "bruja", "cuello": "cuello_capa", "mano": "calabaza"},
    "sanvalentin": {"cabeza": "diadema_corazones", "cuello": "collar_corazon", "mano": "globo_corazon"},
    "patrias": {"cuello": "banda_patria", "mano": "bandera"},
}

# Dónde va cada parte: (x, y, escala) en el dibujo de cada mascota.
_ESQUELETO = {"cabeza": (120, 30, 1.0), "ojos": (120, 116, 1.0), "cuello": (120, 186, 1.0), "mano": (207, 196, 1.0)}
ANCLAS = {
    "panda": _ESQUELETO, "leon": _ESQUELETO, "raton": _ESQUELETO,
    "robot": {"cabeza": (212, 150, 2.3), "ojos": (262, 300, 2.45), "cuello": (210, 425, 2.5), "mano": (378, 430, 2.6)},
}

VALIDOS = {p: {v for v, _, _ in PIEZAS[p]} for p in PARTES}


def leer(texto) -> dict:
    """De lo guardado a {cabeza, ojos, cuello, mano, temporada(bool)}."""
    r = {p: "" for p in PARTES}
    r["temporada"] = True
    r["mostrar"] = None  # None = lo de siempre según el rol (ver mascota_visible)
    if not isinstance(texto, str) or not texto.strip():
        return r
    for par in texto.split(";"):
        k, _, v = par.partition("=")
        k, v = k.strip(), v.strip()
        if k in PARTES and v in VALIDOS[k]:
            r[k] = v
        elif k == "temporada":
            r["temporada"] = v == "1"
        elif k == "mostrar" and v in ("0", "1"):
            r["mostrar"] = v == "1"
    return r


def guardar(cabeza="", ojos="", cuello="", mano="", temporada=True, mostrar=None) -> str:
    vals = {"cabeza": cabeza, "ojos": ojos, "cuello": cuello, "mano": mano}
    partes = [f"{k}={v if v in VALIDOS[k] else ''}" for k, v in vals.items()]
    partes.append(f"temporada={'1' if temporada else '0'}")
    if mostrar is not None:
        partes.append(f"mostrar={'1' if mostrar else '0'}")
    return ";".join(partes)


def mascota_visible(texto, rol: str) -> bool:
    """Los técnicos no tienen mascota a menos que la enciendan en Apariencia;
    los demás la tienen a menos que la apaguen. Los avisos y consejos
    flotantes del sistema salen igual."""
    mostrar = leer(texto)["mostrar"]
    if mostrar is not None:
        return mostrar
    return (rol or "") != "tecnico"


def puesta(texto, hoy: date | None = None) -> dict:
    """Lo que lleva puesto hoy: {parte: clave de pieza}."""
    from app.utils.temas import temporada_de
    if hoy is None:
        from app.utils.turnos_caja import hoy_local
        hoy = hoy_local()
    elegido = leer(texto)
    r = {p: elegido[p] for p in PARTES}
    t = temporada_de(hoy) if elegido["temporada"] else None
    if t:
        r.update(TRAJES_TEMPORADA.get(t, {}))
    return r


def _svg_de(clave: str) -> str:
    if clave in PIEZAS_TEMPORADA:
        return PIEZAS_TEMPORADA[clave]
    for parte in PARTES:
        for v, _, svg in PIEZAS[parte]:
            if v == clave:
                return svg
    return ""


def svg_ropa(mascota: str, piezas: dict, todas: bool = False) -> str:
    """Grupos SVG de la ropa para meter dentro del dibujo de la mascota.
    Con todas=True (pantalla de Apariencia) van todas las piezas y CSS
    muestra solo las elegidas, para probarlas sin recargar."""
    anclas = ANCLAS.get(mascota, _ESQUELETO)
    salida = []
    for parte in PARTES:
        x, y, s = anclas[parte]
        claves = [v for v, _, _ in PIEZAS[parte]] if todas else ([piezas.get(parte)] if piezas.get(parte) else [])
        if todas:
            claves += [c for traje in TRAJES_TEMPORADA.values() for p2, c in traje.items() if p2 == parte]
        for clave in dict.fromkeys(claves):
            svg = _svg_de(clave)
            if svg:
                salida.append(f'<g class="rp rp-{parte} rp-{parte}-{clave}" transform="translate({x},{y}) scale({s})">{svg}</g>')
    return "".join(salida)


def catalogo() -> list[dict]:
    return [{"parte": p, "nombre": NOMBRE_PARTE[p], "piezas": [{"valor": v, "nombre": n} for v, n, _ in PIEZAS[p]]} for p in PARTES]
