"""
NUTS (Nomenclature of Territorial Units for Statistics) reference data.
Used for watchlist NUTS prefix selection with human-readable labels.
Covers Belgium fully (levels 1-3), neighboring countries at level 1-2,
and other EU countries at level 1.
"""
from typing import Optional


# Format: (code, label_fr)
NUTS_REFERENCE: list[tuple[str, str]] = [
    # ── Belgium (complete: level 1, 2, 3) ──
    ("BE1", "Bruxelles-Capitale"),
    ("BE10", "Bruxelles-Capitale"),
    ("BE100", "Arr. de Bruxelles-Capitale"),
    ("BE2", "Flandre"),
    ("BE21", "Prov. Anvers"),
    ("BE211", "Arr. Anvers"),
    ("BE212", "Arr. Malines"),
    ("BE213", "Arr. Turnhout"),
    ("BE22", "Prov. Limbourg (BE)"),
    ("BE221", "Arr. Hasselt"),
    ("BE222", "Arr. Maaseik"),
    ("BE223", "Arr. Tongres"),
    ("BE23", "Prov. Flandre orientale"),
    ("BE231", "Arr. Alost"),
    ("BE232", "Arr. Dendermonde"),
    ("BE233", "Arr. Eeklo"),
    ("BE234", "Arr. Gand"),
    ("BE235", "Arr. Audenaerde"),
    ("BE236", "Arr. Saint-Nicolas"),
    ("BE24", "Prov. Brabant flamand"),
    ("BE241", "Arr. Hal-Vilvorde"),
    ("BE242", "Arr. Louvain"),
    ("BE25", "Prov. Flandre occidentale"),
    ("BE251", "Arr. Bruges"),
    ("BE252", "Arr. Dixmude"),
    ("BE253", "Arr. Ypres"),
    ("BE254", "Arr. Courtrai"),
    ("BE255", "Arr. Ostende"),
    ("BE256", "Arr. Roulers"),
    ("BE257", "Arr. Tielt"),
    ("BE258", "Arr. Furnes"),
    ("BE3", "Wallonie"),
    ("BE31", "Prov. Brabant wallon"),
    ("BE310", "Arr. Nivelles"),
    ("BE32", "Prov. Hainaut"),
    ("BE321", "Arr. Ath"),
    ("BE322", "Arr. Charleroi"),
    ("BE323", "Arr. Mons"),
    ("BE324", "Arr. Mouscron"),
    ("BE325", "Arr. Soignies"),
    ("BE326", "Arr. Thuin"),
    ("BE327", "Arr. Tournai"),
    ("BE33", "Prov. Liège"),
    ("BE331", "Arr. Huy"),
    ("BE332", "Arr. Liège"),
    ("BE334", "Arr. Waremme"),
    ("BE335", "Arr. Verviers"),
    ("BE336", "Communauté germanophone"),
    ("BE34", "Prov. Luxembourg (BE)"),
    ("BE341", "Arr. Arlon"),
    ("BE342", "Arr. Bastogne"),
    ("BE343", "Arr. Marche-en-Famenne"),
    ("BE344", "Arr. Neufchâteau"),
    ("BE345", "Arr. Virton"),
    ("BE35", "Prov. Namur"),
    ("BE351", "Arr. Dinant"),
    ("BE352", "Arr. Namur"),
    ("BE353", "Arr. Philippeville"),

    # ── France (level 1 + 2: régions) ──
    ("FR1", "Île-de-France"),
    ("FR10", "Île-de-France"),
    ("FRB", "Centre — Val de Loire"),
    ("FRC", "Bourgogne-Franche-Comté"),
    ("FRD", "Normandie"),
    ("FRE", "Hauts-de-France"),
    ("FRF", "Grand Est"),
    ("FRG", "Pays de la Loire"),
    ("FRH", "Bretagne"),
    ("FRI", "Nouvelle-Aquitaine"),
    ("FRJ", "Occitanie"),
    ("FRK", "Auvergne-Rhône-Alpes"),
    ("FRL", "Provence-Alpes-Côte d'Azur"),
    ("FRM", "Corse"),
    ("FRY", "Outre-mer"),

    # ── Netherlands (level 1 + 2) ──
    ("NL1", "Noord-Nederland"),
    ("NL11", "Groningen"),
    ("NL12", "Friesland"),
    ("NL13", "Drenthe"),
    ("NL2", "Oost-Nederland"),
    ("NL21", "Overijssel"),
    ("NL22", "Gelderland"),
    ("NL23", "Flevoland"),
    ("NL3", "West-Nederland"),
    ("NL31", "Utrecht"),
    ("NL32", "Noord-Holland"),
    ("NL33", "Zuid-Holland"),
    ("NL34", "Zeeland"),
    ("NL4", "Zuid-Nederland"),
    ("NL41", "Noord-Brabant"),
    ("NL42", "Limburg (NL)"),

    # ── Luxembourg ──
    ("LU0", "Luxembourg"),
    ("LU00", "Luxembourg"),

    # ── Germany (level 1: Bundesländer) ──
    ("DE1", "Baden-Württemberg"),
    ("DE2", "Bayern"),
    ("DE3", "Berlin"),
    ("DE4", "Brandenburg"),
    ("DE5", "Bremen"),
    ("DE6", "Hamburg"),
    ("DE7", "Hessen"),
    ("DE8", "Mecklenburg-Vorpommern"),
    ("DE9", "Niedersachsen"),
    ("DEA", "Nordrhein-Westfalen"),
    ("DEB", "Rheinland-Pfalz"),
    ("DEC", "Saarland"),
    ("DED", "Sachsen"),
    ("DEE", "Sachsen-Anhalt"),
    ("DEF", "Schleswig-Holstein"),
    ("DEG", "Thüringen"),

    # ── Italy (level 1) ──
    ("ITC", "Nord-Ovest"),
    ("ITF", "Sud"),
    ("ITG", "Isole"),
    ("ITH", "Nord-Est"),
    ("ITI", "Centro"),

    # ── Spain (level 1) ──
    ("ES1", "Noroeste"),
    ("ES2", "Noreste"),
    ("ES3", "Comunidad de Madrid"),
    ("ES4", "Centro"),
    ("ES5", "Este"),
    ("ES6", "Sur"),
    ("ES7", "Canarias"),

    # ── Other EU (country level) ──
    ("AT", "Autriche"),
    ("BG", "Bulgarie"),
    ("CY", "Chypre"),
    ("CZ", "Tchéquie"),
    ("DK", "Danemark"),
    ("EE", "Estonie"),
    ("EL", "Grèce"),
    ("FI", "Finlande"),
    ("HR", "Croatie"),
    ("HU", "Hongrie"),
    ("IE", "Irlande"),
    ("LT", "Lituanie"),
    ("LV", "Lettonie"),
    ("MT", "Malte"),
    ("PL", "Pologne"),
    ("PT", "Portugal"),
    ("RO", "Roumanie"),
    ("SE", "Suède"),
    ("SI", "Slovénie"),
    ("SK", "Slovaquie"),
]


def search_nuts(
    query: str = "",
    countries: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, str]]:
    """Search NUTS codes, optionally filtered by country ISO2 codes."""
    q = query.lower().strip()

    # Filter by countries first
    if countries:
        country_uppers = [c.upper().strip() for c in countries if c.strip()]
        filtered = [
            (code, label) for code, label in NUTS_REFERENCE
            if any(code.upper().startswith(c) for c in country_uppers)
        ]
    else:
        filtered = NUTS_REFERENCE

    # Then search by query
    if not q:
        return [{"code": code, "label": label} for code, label in filtered[:limit]]

    results = []
    for code, label in filtered:
        if q in code.lower() or q in label.lower():
            results.append({"code": code, "label": label})
            if len(results) >= limit:
                break
    return results
