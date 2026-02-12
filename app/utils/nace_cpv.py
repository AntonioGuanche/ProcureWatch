"""NACE ↔ CPV correspondence table.

Maps NACE Rev.2 codes (business activity) to CPV 2008 codes (procurement).
Used for profile-based relevance boosting: if a user's company NACE code
matches a notice's CPV code, the notice is more likely relevant.

Mapping granularity: NACE 2-digit division → CPV 2-digit division(s).
Source: EU Commission NACE-CPV correspondence + manual refinement.

Usage:
    from app.utils.nace_cpv import cpv_prefixes_for_nace, nace_matches_cpv

    # Get all CPV prefixes relevant for a NACE code
    prefixes = cpv_prefixes_for_nace("62")  # → ["72", "48"]  (IT services)

    # Check if a specific CPV code matches any of the user's NACE codes
    matches = nace_matches_cpv(["62", "63"], "72212000")  # → True
"""
from typing import Optional

# NACE Rev.2 division (2-digit) → list of CPV 2-digit divisions
# Only includes divisions commonly seen in Belgian public procurement.
NACE_TO_CPV: dict[str, list[str]] = {
    # ── Agriculture, forestry, fishing ──
    "01": ["03", "77"],           # Agricultural products, plantation services
    "02": ["03", "77"],           # Forestry products, forestry services
    "03": ["03", "15"],           # Fish, food products

    # ── Mining, quarrying ──
    "05": ["09", "14"],           # Coal, mining products
    "06": ["09"],                 # Crude petroleum
    "07": ["14"],                 # Metal ores
    "08": ["14", "44"],           # Stone, sand, clay
    "09": ["09", "76"],           # Mining support services

    # ── Manufacturing ──
    "10": ["15"],                 # Food products
    "11": ["15"],                 # Beverages
    "13": ["19"],                 # Textiles
    "14": ["18"],                 # Wearing apparel
    "15": ["19"],                 # Leather
    "16": ["03", "44"],           # Wood products
    "17": ["22", "30"],           # Paper products
    "18": ["22", "79"],           # Printing, reproduction
    "20": ["24", "44"],           # Chemicals
    "21": ["33"],                 # Pharmaceutical products
    "22": ["19", "44"],           # Rubber and plastic
    "23": ["44"],                 # Non-metallic mineral products
    "24": ["14", "44"],           # Basic metals
    "25": ["44"],                 # Fabricated metal products
    "26": ["30", "31", "32", "48"],  # Electronics, computers
    "27": ["31"],                 # Electrical equipment
    "28": ["42", "43"],           # Machinery
    "29": ["34"],                 # Motor vehicles
    "30": ["34", "35"],           # Other transport equipment
    "31": ["39"],                 # Furniture
    "32": ["33", "37"],           # Other manufacturing
    "33": ["50"],                 # Repair/installation of machinery

    # ── Utilities ──
    "35": ["09", "65"],           # Electricity, gas, steam
    "36": ["41", "65"],           # Water collection, treatment
    "37": ["90"],                 # Sewerage
    "38": ["90"],                 # Waste management
    "39": ["90"],                 # Remediation

    # ── Construction ──
    "41": ["45"],                 # Building construction
    "42": ["45"],                 # Civil engineering
    "43": ["45"],                 # Specialised construction

    # ── Wholesale/retail ──
    "45": ["34", "50"],           # Motor vehicle trade/repair
    "46": ["15", "22", "24", "30", "31", "39", "44"],  # Wholesale trade
    "47": ["15", "22", "39"],     # Retail trade

    # ── Transport, logistics ──
    "49": ["60"],                 # Land transport
    "50": ["60"],                 # Water transport
    "51": ["60"],                 # Air transport
    "52": ["63"],                 # Warehousing, logistics support
    "53": ["64"],                 # Postal, courier

    # ── Accommodation, food ──
    "55": ["55"],                 # Accommodation
    "56": ["55"],                 # Food/beverage service

    # ── IT, telecom ──
    "58": ["22", "48"],           # Publishing (incl. software)
    "59": ["92"],                 # Film, video, TV production
    "60": ["92"],                 # Broadcasting
    "61": ["32", "64"],           # Telecommunications
    "62": ["72", "48"],           # Computer programming, consultancy
    "63": ["72"],                 # Information service activities

    # ── Financial ──
    "64": ["66"],                 # Financial services
    "65": ["66"],                 # Insurance
    "66": ["66"],                 # Auxiliary financial services

    # ── Real estate ──
    "68": ["70"],                 # Real estate

    # ── Professional services ──
    "69": ["79"],                 # Legal and accounting
    "70": ["79"],                 # Management consultancy
    "71": ["71"],                 # Architecture, engineering, testing
    "72": ["73"],                 # Scientific R&D
    "73": ["79"],                 # Advertising, market research
    "74": ["79"],                 # Other professional/scientific
    "75": ["85"],                 # Veterinary

    # ── Administrative services ──
    "77": ["34"],                 # Rental and leasing
    "78": ["79"],                 # Employment activities (temp staffing)
    "79": ["63"],                 # Travel agency, tour operator
    "80": ["79"],                 # Security, investigation
    "81": ["90"],                 # Cleaning, landscaping
    "82": ["79"],                 # Office admin, business support

    # ── Public admin ──
    "84": ["75"],                 # Public admin, defence

    # ── Education ──
    "85": ["80"],                 # Education

    # ── Health ──
    "86": ["85", "33"],           # Health (hospitals, medical practice)
    "87": ["85"],                 # Residential care
    "88": ["85"],                 # Social work

    # ── Arts, entertainment ──
    "90": ["92"],                 # Creative arts
    "91": ["92"],                 # Libraries, museums
    "92": ["92"],                 # Gambling
    "93": ["92"],                 # Sports, recreation

    # ── Other services ──
    "94": ["79"],                 # Membership organisations
    "95": ["50"],                 # Repair of goods
    "96": ["98"],                 # Other personal services
}


def cpv_prefixes_for_nace(nace_code: str) -> list[str]:
    """Get CPV division prefixes that correspond to a NACE code.

    Accepts 2-digit (division), 3-digit, or full NACE codes.
    Always matches on the 2-digit division level.
    """
    code = nace_code.strip().replace(".", "")
    division = code[:2] if len(code) >= 2 else code
    return NACE_TO_CPV.get(division, [])


def cpv_prefixes_for_nace_list(nace_csv: Optional[str]) -> set[str]:
    """Get all CPV prefixes for a comma-separated list of NACE codes."""
    if not nace_csv:
        return set()
    result = set()
    for code in nace_csv.split(","):
        code = code.strip()
        if code:
            result.update(cpv_prefixes_for_nace(code))
    return result


def nace_matches_cpv(nace_csv: Optional[str], cpv_code: Optional[str]) -> bool:
    """Check if any of the user's NACE codes correspond to a notice's CPV code.

    Matches at 2-digit CPV division level.
    """
    if not nace_csv or not cpv_code:
        return False

    cpv_clean = cpv_code.replace("-", "").strip()
    if len(cpv_clean) < 2:
        return False

    cpv_division = cpv_clean[:2]
    relevant_cpv_prefixes = cpv_prefixes_for_nace_list(nace_csv)
    return cpv_division in relevant_cpv_prefixes
