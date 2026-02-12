"""Geographic utilities for relevance scoring.

- NUTS code → centroid (lat, lng) for Belgian regions
- Haversine distance between two points
- NUTS-to-distance scoring
"""
import math
from typing import Optional


# ── Belgian NUTS centroids (level 0→3) ──────────────────────────────
# Source: Eurostat NUTS 2024 geometries, approximate centroids.
# Format: NUTS_CODE → (latitude, longitude)

NUTS_CENTROIDS: dict[str, tuple[float, float]] = {
    # Level 0 – Country
    "BE": (50.5039, 4.4699),
    # Level 1 – Regions
    "BE1": (50.8467, 4.3547),    # Bruxelles-Capitale
    "BE2": (51.0500, 4.4000),    # Vlaams Gewest
    "BE3": (50.2500, 4.8000),    # Wallonie
    # Level 2 – Provinces
    "BE10": (50.8467, 4.3547),   # Bruxelles-Capitale
    "BE21": (51.2194, 4.4025),   # Antwerpen
    "BE22": (50.9307, 5.3325),   # Limburg
    "BE23": (51.0543, 3.7174),   # Oost-Vlaanderen
    "BE24": (50.8798, 4.7005),   # Vlaams-Brabant
    "BE25": (51.0500, 3.0000),   # West-Vlaanderen
    "BE31": (50.6700, 4.6100),   # Brabant wallon
    "BE32": (50.4541, 3.9523),   # Hainaut
    "BE33": (50.6292, 5.5797),   # Liège
    "BE34": (49.8500, 5.4700),   # Luxembourg
    "BE35": (50.4669, 4.8674),   # Namur
    # Level 3 – Arrondissements (most common in notices)
    "BE100": (50.8467, 4.3547),  # Arr. Bruxelles-Capitale
    "BE211": (51.2194, 4.4025),  # Arr. Antwerpen
    "BE212": (51.0259, 4.4777),  # Arr. Mechelen
    "BE213": (51.3000, 4.8600),  # Arr. Turnhout
    "BE221": (50.9307, 5.3325),  # Arr. Hasselt
    "BE222": (50.7800, 5.5200),  # Arr. Maaseik
    "BE223": (50.8900, 5.6700),  # Arr. Tongeren
    "BE231": (50.9290, 3.1450),  # Arr. Aalst
    "BE232": (51.0543, 3.9500),  # Arr. Dendermonde
    "BE233": (51.1000, 3.4700),  # Arr. Eeklo
    "BE234": (51.0543, 3.7174),  # Arr. Gent
    "BE235": (50.8500, 3.6100),  # Arr. Oudenaarde
    "BE236": (51.0500, 4.0000),  # Arr. Sint-Niklaas
    "BE241": (50.9000, 4.5300),  # Arr. Halle-Vilvoorde
    "BE242": (50.8798, 4.7005),  # Arr. Leuven
    "BE251": (51.2093, 3.2247),  # Arr. Brugge
    "BE252": (51.0000, 2.8000),  # Arr. Diksmuide
    "BE253": (50.8300, 2.8800),  # Arr. Ieper
    "BE254": (50.8100, 3.2700),  # Arr. Kortrijk
    "BE255": (51.0000, 3.0000),  # Arr. Oostende
    "BE256": (50.9500, 3.1200),  # Arr. Roeselare
    "BE257": (51.0500, 3.1200),  # Arr. Tielt
    "BE258": (51.0700, 2.6600),  # Arr. Veurne
    "BE310": (50.6700, 4.6100),  # Arr. Nivelles
    "BE321": (50.3700, 3.5700),  # Arr. Ath
    "BE322": (50.4108, 4.4446),  # Arr. Charleroi
    "BE323": (50.4500, 3.8400),  # Arr. Mons
    "BE324": (50.3500, 3.6000),  # Arr. Mouscron
    "BE325": (50.5300, 3.6000),  # Arr. Soignies
    "BE326": (50.4400, 3.4400),  # Arr. Thuin
    "BE327": (50.6100, 3.3900),  # Arr. Tournai
    "BE331": (50.5200, 5.8600),  # Arr. Huy
    "BE332": (50.6292, 5.5797),  # Arr. Liège
    "BE334": (50.4900, 5.8700),  # Arr. Waremme
    "BE335": (50.5900, 5.8700),  # Arr. Verviers
    "BE336": (50.6100, 6.0400),  # Arr. Eupen (DG)
    "BE341": (50.0600, 5.5700),  # Arr. Arlon
    "BE342": (49.9300, 5.3000),  # Arr. Bastogne
    "BE343": (50.0600, 5.3600),  # Arr. Marche-en-Famenne
    "BE344": (49.6800, 5.8100),  # Arr. Neufchâteau
    "BE345": (50.1000, 5.5800),  # Arr. Virton
    "BE351": (50.1400, 4.8500),  # Arr. Dinant
    "BE352": (50.4669, 4.8674),  # Arr. Namur
    "BE353": (50.3300, 4.5300),  # Arr. Philippeville
}

# Neighbouring countries – rough centroids for cross-border matching
NUTS_CENTROIDS.update({
    "FR": (46.6034, 1.8883),
    "DE": (51.1657, 10.4515),
    "NL": (52.1326, 5.2913),
    "LU": (49.8153, 6.1296),
})


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in km."""
    R = 6371.0  # Earth radius in km
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    Δφ = math.radians(lat2 - lat1)
    Δλ = math.radians(lon2 - lon1)
    a = math.sin(Δφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(Δλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nuts_centroid(code: str) -> Optional[tuple[float, float]]:
    """Get centroid for a NUTS code. Tries exact match, then progressively shorter prefixes."""
    code = code.strip().upper()
    # Try exact, then progressively shorter
    for length in range(len(code), 1, -1):
        prefix = code[:length]
        if prefix in NUTS_CENTROIDS:
            return NUTS_CENTROIDS[prefix]
    return None


def closest_distance_km(
    user_lat: float,
    user_lng: float,
    nuts_codes: list[str],
) -> Optional[float]:
    """Calculate shortest distance from user location to any of the notice's NUTS regions.

    Returns distance in km, or None if no NUTS code could be resolved.
    """
    best = None
    for code in nuts_codes:
        centroid = nuts_centroid(code)
        if centroid:
            d = haversine_km(user_lat, user_lng, centroid[0], centroid[1])
            if best is None or d < best:
                best = d
    return best
