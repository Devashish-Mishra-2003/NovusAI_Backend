import time
import requests
from typing import List, Optional
from lxml import etree
from app.services.ops_auth import get_access_token

OPS_BASE = "https://ops.epo.org/3.2/rest-services"
USER_AGENT = "NovusAI/1.0 (contact: research@novusai.local)"

REQUEST_DELAY_SEC = 1.2
MAX_SEARCH_RESULTS = 50
MAX_FINAL_PATENTS = 7

NS = {
    "ops": "http://ops.epo.org",
    "ep": "http://www.epo.org/exchange",
}

# 🔒 SECURE XML PARSER
XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    recover=True,
    huge_tree=False
)

def _sleep():
    time.sleep(REQUEST_DELAY_SEC)

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "User-Agent": USER_AGENT,
        "Accept": "application/xml",
    }

def _perform_search(query: str) -> Optional[str]:
    if not query.strip():
        return None

    _sleep()
    url = f"{OPS_BASE}/published-data/search/abstract"
    cql = f"ta = {query.strip()}"

    params = {
        "q": cql,
        "Range": f"1-{MAX_SEARCH_RESULTS}",
    }

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text
    except Exception:
        return None

def search_patents_raw_xml(
    drug: Optional[str],
    conditions: List[str],
) -> str:

    queries = []

    if drug and conditions:
        for c in conditions:
            queries.append(f"{drug} {c}")
    elif drug:
        queries.append(drug)
    elif conditions:
        queries.extend(conditions)

    raw_fragments = []
    for q in queries:
        xml = _perform_search(q)
        if xml:
            raw_fragments.append(xml)

    if not raw_fragments:
        return "NO PATENTS FOUND."

    seen_ids = set()
    docs_with_pub_date = []

    for fragment in raw_fragments:
        try:
            root = etree.fromstring(fragment.encode("utf-8"), parser=XML_PARSER)
        except Exception:
            continue

        for doc in root.xpath("//ep:exchange-document", namespaces=NS):

            country = doc.get("country")
            num = doc.get("doc-number")
            kind = doc.get("kind")

            if not (country and num and kind):
                continue

            pub_id = f"{country}{num}{kind}"
            if pub_id in seen_ids:
                continue
            seen_ids.add(pub_id)

            for abs_elem in doc.xpath(".//ep:abstract[not(@lang='en')]", namespaces=NS):
                abs_elem.getparent().remove(abs_elem)

            if not doc.xpath(".//ep:abstract[@lang='en']", namespaces=NS):
                continue

            pub_date = doc.xpath(
                ".//ep:publication-reference//ep:date/text()",
                namespaces=NS,
            )
            pub_date = pub_date[0] if pub_date else "00000000"

            docs_with_pub_date.append((pub_date, doc))

    docs_with_pub_date.sort(key=lambda x: x[0], reverse=True)

    lines = []
    lines.append("TOP PATENTS — ENGLISH ONLY — RANKED BY PUBLICATION DATE")
    lines.append("=" * 80)

    rank = 1
    for pub_date, doc in docs_with_pub_date[:MAX_FINAL_PATENTS]:

        country = doc.get("country")
        num = doc.get("doc-number")
        kind = doc.get("kind")
        pid = f"{country}{num}{kind}"

        abstract_text = " ".join(
            t.strip()
            for t in doc.xpath(
                ".//ep:abstract[@lang='en']//ep:p//text()", namespaces=NS
            )
            if t.strip()
        )

        lines.append(f"\nRank #{rank}")
        lines.append(f"Patent ID : {pid}")
        lines.append(f"Country   : {country}")
        lines.append(f"Published : {pub_date}")
        lines.append("Abstract:")
        lines.append(abstract_text[:300] if len(abstract_text) > 300 else abstract_text)
        lines.append("-" * 80)

        rank += 1

    return "\n".join(lines)
