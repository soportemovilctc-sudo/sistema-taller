"""Catálogo inicial (semilla) de marcas y modelos de equipos.

Esta lista es un punto de partida curado con los modelos más comunes y
recientes de cada marca (útil para un taller de reparación, donde también
llegan equipos de varias generaciones atrás, no solo los más nuevos).

No pretende ser exhaustiva: desde Configuración > Catálogo de marcas y
modelos se puede agregar cualquier marca o modelo nuevo que salga al
mercado en el futuro, en segundos y sin tocar código.
"""

MARCAS_SEED = {
    # --- Celulares ---
    "SAMSUNG": [
        "Galaxy S26", "Galaxy S26+", "Galaxy S26 Ultra",
        "Galaxy S25", "Galaxy S25+", "Galaxy S25 Ultra", "Galaxy S25 Edge",
        "Galaxy S24", "Galaxy S24+", "Galaxy S24 Ultra", "Galaxy S24 FE",
        "Galaxy S23", "Galaxy S23+", "Galaxy S23 Ultra", "Galaxy S23 FE",
        "Galaxy S22", "Galaxy S22 Ultra", "Galaxy S21", "Galaxy S21 Ultra",
        "Galaxy Z Fold6", "Galaxy Z Fold5", "Galaxy Z Flip6", "Galaxy Z Flip5",
        "Galaxy A06", "Galaxy A16", "Galaxy A26", "Galaxy A36", "Galaxy A56",
        "Galaxy A15", "Galaxy A25", "Galaxy A55", "Galaxy A14", "Galaxy A54",
        "Galaxy A13", "Galaxy A53", "Galaxy A34", "Galaxy A12", "Galaxy A32",
        "Galaxy M14", "Galaxy M34", "Galaxy Note 20", "Galaxy Note 10",
    ],
    "SAMSUNG GALAXY TAB": [
        "Galaxy Tab S10", "Galaxy Tab S10+", "Galaxy Tab S10 Ultra",
        "Galaxy Tab S9", "Galaxy Tab S9+", "Galaxy Tab S9 Ultra", "Galaxy Tab S9 FE",
        "Galaxy Tab S8", "Galaxy Tab S6 Lite", "Galaxy Tab A9", "Galaxy Tab A9+",
        "Galaxy Tab A8", "Galaxy Tab A7",
    ],
    "MOTOROLA": [
        "Edge 60", "Edge 60 Pro", "Edge 50", "Edge 50 Pro", "Edge 40",
        "Edge 30", "Moto G85", "Moto G75", "Moto G65", "Moto G55", "Moto G45",
        "Moto G35", "Moto G34", "Moto G24", "Moto G Stylus", "Moto G Power",
        "Moto G Play", "Razr 60", "Razr 60 Ultra", "Razr 50", "Razr 40",
    ],
    "APPLE": [
        "iPhone 17", "iPhone 17 Pro", "iPhone 17 Pro Max", "iPhone Air",
        "iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro", "iPhone 16 Pro Max", "iPhone 16e",
        "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max",
        "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max",
        "iPhone 13", "iPhone 13 mini", "iPhone 13 Pro", "iPhone 13 Pro Max",
        "iPhone 12", "iPhone 12 mini", "iPhone 12 Pro", "iPhone 12 Pro Max",
        "iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max",
        "iPhone SE (2020)", "iPhone SE (2022)", "iPhone SE (2024)",
        "iPhone XR", "iPhone XS", "iPhone XS Max", "iPhone X",
    ],
    "REDMI": [
        "Redmi Note 14", "Redmi Note 14 Pro", "Redmi Note 13", "Redmi Note 13 Pro",
        "Redmi Note 12", "Redmi Note 12 Pro", "Redmi Note 11", "Redmi Note 11 Pro",
        "Redmi 15", "Redmi 14", "Redmi 13", "Redmi 13C", "Redmi 12", "Redmi 12C",
        "Redmi 10", "Redmi 9", "Redmi A5", "Redmi A3", "Redmi A2",
    ],
    "XIAOMI": [
        "Xiaomi 15", "Xiaomi 15 Ultra", "Xiaomi 14", "Xiaomi 14 Ultra", "Xiaomi 14T",
        "Xiaomi 13", "Xiaomi 13T", "Xiaomi 13 Pro", "Xiaomi 12", "Xiaomi 12T",
        "Xiaomi 11T", "Mi 11", "Mi 10", "Mi 9",
    ],
    "XIAOMI PAD": ["Xiaomi Pad 7", "Xiaomi Pad 7 Pro", "Xiaomi Pad 6", "Xiaomi Pad 6 Pro", "Xiaomi Pad 5"],
    "POCO": [
        "Poco X7", "Poco X7 Pro", "Poco X6", "Poco X6 Pro", "Poco X5", "Poco X5 Pro",
        "Poco F6", "Poco F6 Pro", "Poco F5", "Poco M6 Pro", "Poco M6", "Poco M5",
        "Poco C65", "Poco C55",
    ],
    "HONOR": [
        "Honor Magic7", "Honor Magic6", "Honor X9b", "Honor X8b", "Honor X7b", "Honor X6b",
        "Honor 200", "Honor 90", "Honor 70", "Honor Pad 9",
    ],
    "GOOGLE PIXEL": [
        "Pixel 10", "Pixel 10 Pro", "Pixel 9", "Pixel 9 Pro", "Pixel 9 Pro XL", "Pixel 9a",
        "Pixel 8", "Pixel 8 Pro", "Pixel 8a", "Pixel 7", "Pixel 7 Pro", "Pixel 7a",
        "Pixel 6", "Pixel 6 Pro", "Pixel 6a",
    ],
    "HUAWEI": [
        "P70", "P70 Pro", "P60", "P60 Pro", "P50", "Mate 60", "Mate 60 Pro", "Mate 50",
        "Nova 12", "Nova 11", "Nova 10", "Y9", "Y7",
    ],
    "HUAWEI MATEPAD": ["MatePad Pro", "MatePad 11", "MatePad SE", "MatePad T10"],
    "NOKIA": [
        "Nokia G42", "Nokia G22", "Nokia C32", "Nokia C22", "Nokia X30", "Nokia XR21",
        "Nokia 105", "Nokia 110", "Nokia 150", "Nokia 3210 (2024)",
    ],
    "SONY": ["Xperia 1 VI", "Xperia 1 V", "Xperia 5 V", "Xperia 10 VI", "Xperia 10 V"],
    "ALCATEL": ["Alcatel 1L", "Alcatel 1B", "Alcatel 3L", "Alcatel 3X", "Alcatel Volta"],
    "ZTE": ["ZTE Blade A75", "ZTE Blade A55", "ZTE Blade V50", "ZTE Blade V40"],
    "TCL": ["TCL 40", "TCL 40 SE", "TCL 50", "TCL 50 SE", "TCL 30", "TCL 305", "TCL 403"],
    "REALME": [
        "Realme 14", "Realme 13", "Realme 12", "Realme 11", "Realme C67", "Realme C65",
        "Realme C55", "Realme GT 6", "Realme Narzo 70",
    ],
    "OPPO": ["Reno 12", "Reno 11", "OPPO A98", "OPPO A78", "OPPO A58", "Find X7"],
    "VIVO": ["Vivo V30", "Vivo V29", "Vivo Y28", "Vivo Y27", "Vivo Y17s", "Vivo X100"],
    "TECNO": ["Spark 20", "Spark 10", "Camon 30", "Camon 20", "Pova 6", "Pop 8"],
    "NOTHING": ["Phone (1)", "Phone (2)", "Phone (2a)", "Phone (3)", "Phone (3a)"],
    "CMF": ["CMF Phone 1", "CMF Phone 2 Pro"],
    "ONEPLUS": ["OnePlus 13", "OnePlus 12", "OnePlus 12R", "OnePlus 11", "Nord 4", "Nord CE4", "Nord 3"],
    "BLACKBERRY": ["Key2", "KeyOne", "Classic", "Passport"],
    "MEIZU": ["Meizu 21", "Meizu 20", "Meizu 18", "Meizu Note 9"],
    "REDMAGIC": ["RedMagic 10 Pro", "RedMagic 9 Pro", "RedMagic 9S Pro", "RedMagic 8 Pro"],
    "NUBIA": ["Nubia Z60 Ultra", "Nubia Z50", "Nubia Flip", "Nubia Focus"],
    "PHILCO": [],
    "LG": ["LG G8", "LG G7", "LG V60", "LG V50", "LG K51", "LG K41s", "LG Stylo 6", "LG Velvet"],
    "INFINIX": ["Note 40", "Note 30", "Hot 50", "Hot 40", "Smart 9", "Zero 30"],
    "ITEL": ["itel A70", "itel A60", "itel S23", "itel P55", "itel Vision 3"],
    "BLU": ["BLU G91", "BLU G71", "BLU View 3", "BLU Studio X"],
    "QLINK": [],
    "SKY": ["Sky Elite", "Sky Fuego", "Sky Platinum"],
    "INOI": ["Inoi 2 Lite", "Inoi 3 Lite"],
    # --- Tablets adicionales ---
    "AMAZON FIRE": ["Fire 7", "Fire HD 8", "Fire HD 10", "Fire Max 11"],
    "TCL TAB": ["TCL Tab 10", "TCL Tab 8"],
    "ALCATEL TAB": ["Alcatel 1T", "Alcatel Join Tab", "Alcatel 3T"],
    "LENOVO TAB": ["Tab M11", "Tab M10", "Tab P11", "Tab P12", "Yoga Tab"],
    "ITEL TAB": ["itel Pad One"],
    "SKY PAD": [],
    # --- Laptops / PC ---
    "LENOVO": ["ThinkPad", "IdeaPad", "Legion", "Yoga", "ThinkBook"],
    "DELL": ["Inspiron", "Latitude", "XPS", "Vostro", "Alienware"],
    "HP": ["Pavilion", "EliteBook", "ProBook", "Omen", "Envy", "HP 15"],
    "TOSHIBA": ["Satellite", "Portege", "Tecra"],
    "ACER": ["Aspire", "Swift", "Nitro", "Predator", "TravelMate"],
    "APPLE MAC": ["MacBook Air M2", "MacBook Air M3", "MacBook Air M4", "MacBook Pro 14", "MacBook Pro 16", "iMac", "Mac mini", "Mac Studio"],
    "APPLE IPAD": ["iPad Pro 11", "iPad Pro 13", "iPad Air", "iPad (10.ª gen)", "iPad (11.ª gen)", "iPad mini"],
    "RAZER": ["Razer Blade 14", "Razer Blade 16", "Razer Phone 2"],
    # --- Consolas ---
    "PLAYSTATION": ["PS3", "PS4", "PS4 Slim", "PS4 Pro", "PS5", "PS5 Digital", "PS5 Slim", "PS5 Pro"],
    "XBOX": ["Xbox 360", "Xbox One", "Xbox One S", "Xbox One X", "Xbox Series S", "Xbox Series X"],
    "FCC": [],
    # --- Audio ---
    "JBL": ["JBL Flip 6", "JBL Charge 5", "JBL Go 3", "JBL Xtreme 3", "JBL Clip 4"],
    "SONY AUDIO": ["WH-1000XM5", "WF-1000XM5", "SRS-XB43"],
    # --- Impresoras ---
    "HP PRINTER": ["HP DeskJet", "HP OfficeJet", "HP LaserJet", "HP Ink Tank"],
    "CANON": ["Canon Pixma", "Canon imageCLASS"],
    "EPSON": ["Epson EcoTank", "Epson WorkForce", "Epson Expression"],
    "BROTHER": ["Brother HL", "Brother DCP", "Brother MFC"],
    "SAMSUNG PRINTER": ["Samsung Xpress"],
    "RICOH": ["Ricoh Aficio", "Ricoh MP"],
    # --- Monitores ---
    "SAMSUNG MONITOR": ["Odyssey", "ViewFinity"],
    "LG MONITOR": ["UltraGear", "UltraWide", "UltraFine"],
    "HP MONITOR": ["HP EliteDisplay", "HP 24mh"],
    "ACER MONITOR": ["Nitro", "Predator"],
    "ASUS MONITOR": ["ROG Swift", "TUF Gaming", "ProArt"],
    "VIEWSONIC": ["ViewSonic VX", "ViewSonic VA"],
    "PHILIPS MONITOR": ["Philips Serie 1", "Philips Serie 2"],
    # --- Genéricos (siempre disponibles como salida) ---
    "OTRA MARCA": [],
    "SIN MARCA": [],
    "OTRO EQUIPO": [],
}
