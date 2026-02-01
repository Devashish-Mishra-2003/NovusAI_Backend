import time
import logging
from typing import List, Dict, Optional, Literal
import requests
from xml.etree import ElementTree as ET
import os

logger = logging.getLogger("pubmed-service")

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_DB = "pubmed"
NCBI_TOOL = "novusai-literature-agent"
NCBI_EMAIL = os.getenv("NCBI_EMAIL", "novusai@example.com")

QueryMode = Literal["DRUG_ONLY", "CONDITION_ONLY", "DRUG_AND_CONDITION"]

# -------------------------------------------------
# RATE LIMITING
# -------------------------------------------------

_LAST_CALL = 0.0

def _throttle(min_interval: float = 0.35) -> None:
    global _LAST_CALL
    now = time.time()
    elapsed = now - _LAST_CALL
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _LAST_CALL = time.time()

# -------------------------------------------------
# SAFE XML PARSER
# -------------------------------------------------

def _safe_parse_xml(text: str):
    try:
        return ET.fromstring(text)
    except Exception:
        logger.warning("⚠️ Failed to parse PubMed XML safely")
        return None

# -------------------------------------------------
# QUERY BUILDER
# -------------------------------------------------

def build_pubmed_query(
    drug: Optional[str],
    conditions: List[str],
    mode: QueryMode,
) -> str:

    if mode == "DRUG_ONLY":
        return f"\"{drug}\"[tiab]"

    if mode == "CONDITION_ONLY":
        return " OR ".join(f"\"{c}\"[tiab]" for c in conditions)

    if mode == "DRUG_AND_CONDITION":
        cond_block = " OR ".join(f"\"{c}\"[tiab]" for c in conditions)
        return f"\"{drug}\"[tiab] AND ({cond_block})"

    raise ValueError(f"Unsupported query mode: {mode}")

# -------------------------------------------------
# SEARCH (PMIDs)
# -------------------------------------------------

def search_pubmed_ids(
    query: str,
    retmax: int = 50,
    sort: str = "pub+date",
) -> List[str]:

    params = {
        "db": NCBI_DB,
        "term": query,
        "retmax": str(retmax),
        "retmode": "xml",
        "sort": sort,
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    _throttle()
    resp = requests.get(f"{NCBI_BASE}/esearch.fcgi", params=params, timeout=15)
    resp.raise_for_status()

    root = _safe_parse_xml(resp.text)
    if root is None:
        return []

    return [e.text for e in root.findall(".//Id") if e.text]

# -------------------------------------------------
# SUMMARIES
# -------------------------------------------------

def fetch_pubmed_summaries(pmids: List[str]) -> List[Dict]:
    if not pmids:
        return []

    params = {
        "db": NCBI_DB,
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    _throttle()
    resp = requests.get(f"{NCBI_BASE}/esummary.fcgi", params=params, timeout=20)
    resp.raise_for_status()

    root = _safe_parse_xml(resp.text)
    if root is None:
        return []

    out: List[Dict] = []

    for doc in root.findall(".//DocSum"):
        pmid_elem = doc.find("Id")
        if pmid_elem is None or not pmid_elem.text:
            continue

        pmid = pmid_elem.text
        title = ""
        journal = ""
        pubdate = ""
        article_types: List[str] = []

        for item in doc.findall("Item"):
            name = item.get("Name")
            if name == "Title":
                title = item.text or ""
            elif name == "FullJournalName":
                journal = item.text or ""
            elif name == "PubDate":
                pubdate = item.text or ""
            elif name == "PubTypeList":
                for pt in item.findall("Item"):
                    if pt.text:
                        article_types.append(pt.text)

        year = None
        for token in pubdate.split():
            if token.isdigit() and len(token) == 4:
                year = int(token)
                break

        out.append({
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "publication_year": year,
            "article_types": article_types,
        })

    logger.info(f"✅ Parsed {len(out)} summaries from DocSum")
    return out

# -------------------------------------------------
# ABSTRACTS (BATCH SAFE)
# -------------------------------------------------

def fetch_pubmed_abstracts(pmids: List[str]) -> Dict[str, str]:
    if not pmids:
        return {}

    abstracts: Dict[str, str] = {}
    BATCH_SIZE = 5

    for i in range(0, len(pmids), BATCH_SIZE):
        batch = pmids[i:i + BATCH_SIZE]

        params = {
            "db": NCBI_DB,
            "id": ",".join(batch),
            "retmode": "xml",
            "rettype": "abstract",
            "tool": NCBI_TOOL,
            "email": NCBI_EMAIL,
        }

        try:
            _throttle()
            resp = requests.get(
                f"{NCBI_BASE}/efetch.fcgi",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()

            root = _safe_parse_xml(resp.text)
            if root is None:
                continue

            for article in root.findall(".//PubmedArticle"):
                pmid_elem = article.find(".//PMID")
                if pmid_elem is None or not pmid_elem.text:
                    continue

                parts = []
                for ab in article.findall(".//Abstract/AbstractText"):
                    if ab.text:
                        parts.append(ab.text)

                abstracts[pmid_elem.text] = " ".join(parts).strip()

        except Exception as e:
            logger.warning(f"⚠️ efetch failed for PMIDs {batch}: {e}")
            continue

    return abstracts

# -------------------------------------------------
# MeSH TERMS
# -------------------------------------------------

def fetch_mesh_terms(pmids: List[str]) -> Dict[str, List[str]]:
    if not pmids:
        return {}

    params = {
        "db": NCBI_DB,
        "id": ",".join(pmids),
        "retmode": "xml",
        "rettype": "medline",
        "tool": NCBI_TOOL,
        "email": NCBI_EMAIL,
    }

    _throttle()
    resp = requests.get(f"{NCBI_BASE}/efetch.fcgi", params=params, timeout=20)
    resp.raise_for_status()

    root = _safe_parse_xml(resp.text)
    if root is None:
        return {}

    mesh_map: Dict[str, List[str]] = {}

    for article in root.findall(".//PubmedArticle"):
        pmid_elem = article.find(".//PMID")
        if pmid_elem is None or not pmid_elem.text:
            continue

        terms: List[str] = []
        for mh in article.findall(".//MeshHeading/DescriptorName"):
            if mh.text:
                terms.append(mh.text)

        mesh_map[pmid_elem.text] = terms

    return mesh_map

# -------------------------------------------------
# POPULATION INFERENCE
# -------------------------------------------------

def infer_population_flag_from_mesh_and_text(
    mesh_terms: List[str],
    abstract: str,
) -> str:

    mesh_lower = [m.lower() for m in mesh_terms]
    text = (abstract or "").lower()

    veterinary_markers = [
        "veterinary", "canine", "feline", "equine", "bovine",
        "dog ", "dogs ", "cat ", "cats ", "horse", "cattle"
    ]

    if any(t in text for t in veterinary_markers):
        return "VETERINARY_ONLY"

    if "humans" in mesh_lower or "human" in text:
        return "HUMAN"

    if "animals" in mesh_lower:
        return "ANIMAL_PRECLINICAL"

    return "UNKNOWN"
