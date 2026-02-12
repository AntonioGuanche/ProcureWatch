"""
Parse BOSA CAN eForms XML to extract award data.

BOSA CAN (type 29) notices store eForms XML in:
  raw_data["versions"][-1]["notice"]["xmlContent"]

This module extracts:
  - award_winner_name  (from efac:TenderingParty → Tenderer → Organizations)
  - award_value        (from efac:NoticeResult > cbc:TotalAmount)
  - award_date         (from cac:TenderResult > cbc:AwardDate)
  - number_tenders_received (from efac:ReceivedSubmissionsStatistics)
  - award_criteria_json (structured summary of lots, winners, amounts)
"""
import logging
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

logger = logging.getLogger(__name__)

# eForms XML namespaces
NS = {
    "can": "urn:oasis:names:specification:ubl:schema:xsd:ContractAwardNotice-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "efac": "http://data.europa.eu/p27/eforms-ubl-extension-aggregate-components/1",
    "efbc": "http://data.europa.eu/p27/eforms-ubl-extension-basic-components/1",
    "efext": "http://data.europa.eu/p27/eforms-ubl-extensions/1",
}


def extract_xml_from_raw_data(raw_data: dict) -> Optional[str]:
    """Get the xmlContent from the latest version in raw_data."""
    versions = raw_data.get("versions")
    if not versions or not isinstance(versions, list):
        return None

    # Take the latest version (last published)
    for v in reversed(versions):
        if not isinstance(v, dict):
            continue
        notice = v.get("notice")
        if not notice:
            continue
        # notice can be a dict with xmlContent, or possibly a string
        if isinstance(notice, dict):
            xml_content = notice.get("xmlContent")
            if xml_content and isinstance(xml_content, str) and xml_content.startswith("<?xml"):
                return xml_content
        elif isinstance(notice, str) and "xmlContent=" in notice:
            # Fallback: if stored as stringified object, extract XML
            idx = notice.find("<?xml")
            if idx >= 0:
                # Find end — the XML ends at the closing tag
                end_markers = ["</ContractAwardNotice>", "; version=", "; noticeVersion="]
                end_idx = len(notice)
                for marker in end_markers:
                    pos = notice.find(marker, idx)
                    if pos > 0:
                        if marker.startswith("</"):
                            end_idx = min(end_idx, pos + len(marker))
                        else:
                            end_idx = min(end_idx, pos)
                return notice[idx:end_idx]
    return None


def parse_award_data(xml_content: str) -> dict[str, Any]:
    """
    Parse eForms CAN XML and extract award fields.

    Returns dict with keys:
      - total_amount: Decimal or None
      - currency: str or None
      - award_date: date or None
      - winners: list of {name, org_id, size, country, amount, lot_id}
      - tenders_received: int or None (total across lots)
      - lots: list of {lot_id, result_id, high_amount, low_amount, tenders, winner_tender_id}
      - contracts: list of {contract_id, issue_date, tender_id}
    """
    result: dict[str, Any] = {
        "total_amount": None,
        "currency": None,
        "award_date": None,
        "winners": [],
        "tenders_received": None,
        "lots": [],
        "contracts": [],
    }

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.warning("XML parse error: %s", e)
        return result

    # ── 1. Find NoticeResult inside EformsExtension ───────────────
    notice_result = root.find(
        ".//efext:EformsExtension/efac:NoticeResult", NS
    )
    if notice_result is None:
        logger.debug("No efac:NoticeResult found in XML")
        return result

    # ── 2. Total amount ───────────────────────────────────────────
    total_el = notice_result.find("cbc:TotalAmount", NS)
    if total_el is not None and total_el.text:
        try:
            result["total_amount"] = Decimal(total_el.text.strip())
            result["currency"] = total_el.get("currencyID", "EUR")
        except InvalidOperation:
            pass

    # ── 3. Organizations lookup table: org_id → {name, size, country}
    orgs: dict[str, dict[str, str]] = {}
    for org_el in root.findall(".//efac:Organizations/efac:Organization", NS):
        company = org_el.find("efac:Company", NS)
        if company is None:
            continue
        org_id_el = company.find("cac:PartyIdentification/cbc:ID", NS)
        if org_id_el is None or not org_id_el.text:
            continue
        org_id = org_id_el.text.strip()

        # Get name (prefer FR, then first available)
        names = company.findall("cac:PartyName/cbc:Name", NS)
        name = _pick_name(names, prefer_lang="FRA")

        # Size
        size_el = company.find("efbc:CompanySizeCode", NS)
        size = size_el.text.strip() if size_el is not None and size_el.text else None

        # Country
        country_el = company.find(
            "cac:PostalAddress/cac:Country/cbc:IdentificationCode", NS
        )
        country = (
            country_el.text.strip()
            if country_el is not None and country_el.text
            else None
        )

        orgs[org_id] = {"name": name, "size": size, "country": country}

    # ── 4. TenderingParty → Tenderer mapping (who won which tender)
    # tendering_party_id → list of org_ids
    tp_tenderers: dict[str, list[str]] = {}
    for tp in notice_result.findall("efac:TenderingParty", NS):
        tp_id_el = tp.find("cbc:ID", NS)
        if tp_id_el is None or not tp_id_el.text:
            continue
        tp_id = tp_id_el.text.strip()
        tenderer_ids = []
        for tenderer in tp.findall("efac:Tenderer/cbc:ID", NS):
            if tenderer.text:
                tenderer_ids.append(tenderer.text.strip())
        tp_tenderers[tp_id] = tenderer_ids

    # ── 5. LotTender: tender_id → {amount, tp_id, lot_id}
    tenders: dict[str, dict[str, Any]] = {}
    for lt in notice_result.findall("efac:LotTender", NS):
        tid_el = lt.find("cbc:ID", NS)
        if tid_el is None or not tid_el.text:
            continue
        tid = tid_el.text.strip()
        amount_el = lt.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
        amount = None
        if amount_el is not None and amount_el.text:
            try:
                amount = Decimal(amount_el.text.strip())
            except InvalidOperation:
                pass
        tp_id_el = lt.find("efac:TenderingParty/cbc:ID", NS)
        tp_id = tp_id_el.text.strip() if tp_id_el is not None and tp_id_el.text else None

        lot_el = lt.find("efac:TenderLot/cbc:ID", NS)
        lot_id = lot_el.text.strip() if lot_el is not None and lot_el.text else None

        ref_el = lt.find("efac:TenderReference/cbc:ID", NS)
        ref = ref_el.text.strip() if ref_el is not None and ref_el.text else None

        tenders[tid] = {
            "amount": amount,
            "tp_id": tp_id,
            "lot_id": lot_id,
            "reference": ref,
        }

    # ── 6. LotResult: lot results with winner tender refs
    total_tenders = 0
    for lr in notice_result.findall("efac:LotResult", NS):
        res_id_el = lr.find("cbc:ID", NS)
        res_id = res_id_el.text.strip() if res_id_el is not None and res_id_el.text else None

        lot_el = lr.find("efac:TenderLot/cbc:ID", NS)
        lot_id = lot_el.text.strip() if lot_el is not None and lot_el.text else None

        high_el = lr.find("cbc:HigherTenderAmount", NS)
        high = _decimal_or_none(high_el)
        low_el = lr.find("cbc:LowerTenderAmount", NS)
        low = _decimal_or_none(low_el)

        # Number of tenders for this lot
        stats = lr.find("efac:ReceivedSubmissionsStatistics", NS)
        lot_tenders = None
        if stats is not None:
            num_el = stats.find("efbc:StatisticsNumeric", NS)
            if num_el is not None and num_el.text:
                try:
                    lot_tenders = int(num_el.text.strip())
                    total_tenders += lot_tenders
                except ValueError:
                    pass

        # Winner tender ID
        winner_tid_el = lr.find("efac:LotTender/cbc:ID", NS)
        winner_tid = (
            winner_tid_el.text.strip()
            if winner_tid_el is not None and winner_tid_el.text
            else None
        )

        result["lots"].append({
            "result_id": res_id,
            "lot_id": lot_id,
            "high_amount": str(high) if high else None,
            "low_amount": str(low) if low else None,
            "tenders_received": lot_tenders,
            "winner_tender_id": winner_tid,
        })

    if total_tenders > 0:
        result["tenders_received"] = total_tenders

    # ── 7. SettledContract: contract details
    for sc in notice_result.findall("efac:SettledContract", NS):
        cid_el = sc.find("cbc:ID", NS)
        cid = cid_el.text.strip() if cid_el is not None and cid_el.text else None
        issue_el = sc.find("cbc:IssueDate", NS)
        issue_date = issue_el.text.strip() if issue_el is not None and issue_el.text else None
        ref_el = sc.find("efac:ContractReference/cbc:ID", NS)
        ref = ref_el.text.strip() if ref_el is not None and ref_el.text else None
        tender_el = sc.find("efac:LotTender/cbc:ID", NS)
        tender_id = tender_el.text.strip() if tender_el is not None and tender_el.text else None

        result["contracts"].append({
            "contract_id": cid,
            "issue_date": issue_date,
            "reference": ref,
            "tender_id": tender_id,
        })

    # ── 8. Resolve winners: combine tender→tp→org
    seen_winners: set[str] = set()
    for tid, tender_info in tenders.items():
        tp_id = tender_info.get("tp_id")
        if not tp_id or tp_id not in tp_tenderers:
            continue
        for org_id in tp_tenderers[tp_id]:
            if org_id in seen_winners:
                continue
            seen_winners.add(org_id)
            org_info = orgs.get(org_id, {})
            if org_info.get("name"):
                result["winners"].append({
                    "name": org_info["name"],
                    "org_id": org_id,
                    "size": org_info.get("size"),
                    "country": org_info.get("country"),
                    "amount": str(tender_info["amount"]) if tender_info.get("amount") else None,
                    "lot_id": tender_info.get("lot_id"),
                })

    # ── 9. Award date from TenderResult
    award_date_el = root.find(".//cac:TenderResult/cbc:AwardDate", NS)
    if award_date_el is not None and award_date_el.text:
        raw_date = award_date_el.text.strip()
        # Format: "2025-12-01+01:00" or "2025-12-01"
        result["award_date"] = _parse_date(raw_date)

    return result


def build_notice_fields(parsed: dict[str, Any]) -> dict[str, Any]:
    """
    Convert parsed award data into ProcurementNotice field updates.
    Returns dict with only non-None fields to set.
    """
    updates: dict[str, Any] = {}

    # award_winner_name: join all winner names (max 500 chars)
    if parsed.get("winners"):
        names = [w["name"] for w in parsed["winners"] if w.get("name")]
        if names:
            winner_str = " | ".join(names)
            updates["award_winner_name"] = winner_str[:500]

    # award_value: total amount
    if parsed.get("total_amount") is not None:
        updates["award_value"] = parsed["total_amount"]

    # award_date: skip placeholder dates like 2000-01-01
    if parsed.get("award_date"):
        d = parsed["award_date"]
        if isinstance(d, date) and d.year >= 2010:
            updates["award_date"] = d

    # number_tenders_received
    if parsed.get("tenders_received") is not None:
        updates["number_tenders_received"] = parsed["tenders_received"]

    # award_criteria_json: structured summary
    criteria: dict[str, Any] = {}
    if parsed.get("currency"):
        criteria["currency"] = parsed["currency"]
    if parsed.get("lots"):
        criteria["lots"] = parsed["lots"]
    if parsed.get("contracts"):
        criteria["contracts"] = parsed["contracts"]
    if parsed.get("winners"):
        criteria["winners"] = parsed["winners"]
    if criteria:
        updates["award_criteria_json"] = criteria

    return updates


# ── Helpers ───────────────────────────────────────────────────────────


def _pick_name(name_elements: list, prefer_lang: str = "FRA") -> Optional[str]:
    """Pick best name from a list of <cbc:Name languageID='...'> elements."""
    if not name_elements:
        return None
    preferred = None
    fallback = None
    for el in name_elements:
        lang = el.get("languageID", "")
        text = el.text.strip() if el.text else ""
        if not text:
            continue
        if lang == prefer_lang:
            preferred = text
        elif fallback is None:
            fallback = text
    return preferred or fallback


def _decimal_or_none(el) -> Optional[Decimal]:
    if el is not None and el.text:
        try:
            return Decimal(el.text.strip())
        except InvalidOperation:
            return None
    return None


def _parse_date(raw: str) -> Optional[date]:
    """Parse date from '2025-12-01+01:00' or '2025-12-01' format."""
    try:
        # Strip timezone offset if present
        clean = raw.split("+")[0].split("T")[0].strip()
        parts = clean.split("-")
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        pass
    return None
