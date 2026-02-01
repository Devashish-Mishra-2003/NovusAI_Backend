import logging
import re
import requests
from typing import List, Set

logger = logging.getLogger("condition-synonyms")
logger.setLevel(logging.INFO)

OLS_BASE_URL = "https://www.ebi.ac.uk/ols4/api"
ALLOWED_ONTOLOGIES = {"mondo", "doid", "mesh"}


def _normalize(text: str) -> str:
    """
    Canonicalize synonym text:
    - lowercase
    - remove parentheticals
    - split composite labels
    - choose most descriptive fragment
    """
    text = text.lower()
    text = re.sub(r"\s*\([^)]*\)", "", text)

    # Split composite labels like:
    # "nash - nonalcoholic steatohepatitis"
    parts = re.split(r"\s*[-:/,]\s*", text)

    # Choose longest fragment (most descriptive)
    text = max(parts, key=len)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_acronyms(raw_synonyms: List[str]) -> Set[str]:
    """
    Extract canonical medical acronyms (MASH, COPD, ALS, etc.)
    BEFORE normalization.
    """
    acronyms = set()
    for s in raw_synonyms:
        if s.isupper() and s.isalpha() and 3 <= len(s) <= 6:
            acronyms.add(s.lower())
    return acronyms


def _is_valid_disease_name(text: str, acronyms: Set[str]) -> bool:
    """
    Accept if:
    - canonical acronym (e.g., mash, copd)
    OR
    - full-form disease name (length >= 8)
    Reject numeric junk and definition fragments.
    """

    # Reject numeric / code-like junk
    if text.isdigit():
        return False

    if not any(c.isalpha() for c in text):
        return False

    # Reject definition-like endings
    for bad_end in (" in", " of", " for", " with"):
        if text.endswith(bad_end):
            return False

    # Accept canonical acronym
    if text in acronyms:
        return True

    # Accept full-form disease names
    if len(text) >= 8:
        return True

    return False


def expand_condition(condition: str) -> List[str]:
    """
    Input  : condition (str)
    Output : List[str] -> [base, synonym1, synonym2]
    """

    logger.info("=== EBI OLS SYNONYM EXPANSION START ===")
    logger.info("Input condition: %s", condition)

    base = _normalize(condition)

    # ---------- STEP 1: SEARCH ----------
    search_resp = requests.get(
        f"{OLS_BASE_URL}/search",
        params={
            "q": base,
            "ontology": ",".join(ALLOWED_ONTOLOGIES),
            "rows": 1,
        },
        timeout=10,
    )
    search_resp.raise_for_status()

    docs = search_resp.json().get("response", {}).get("docs", [])
    if not docs:
        return [base]

    doc = docs[0]
    iri = doc.get("iri")
    ontology = doc.get("ontology_name")

    if not iri or not ontology:
        return [base]

    # ---------- STEP 2: FETCH TERM ----------
    term_resp = requests.get(
        f"{OLS_BASE_URL}/ontologies/{ontology}/terms",
        params={"iri": iri},
        timeout=10,
    )
    term_resp.raise_for_status()

    terms = term_resp.json().get("_embedded", {}).get("terms", [])
    if not terms:
        return [base]

    term = terms[0]
    raw_synonyms = term.get("synonyms", [])

    # ---------- STEP 3: ACRONYM EXTRACTION ----------
    acronyms = _extract_acronyms(raw_synonyms)

    # ---------- STEP 4: NORMALIZE + VALIDATE (MAX 20) ----------
    normalized = []
    for s in raw_synonyms[:20]:
        norm = _normalize(s)
        if norm and _is_valid_disease_name(norm, acronyms):
            normalized.append(norm)

    # De-duplicate, preserve order
    normalized = list(dict.fromkeys(normalized))

    # Remove base if repeated
    normalized = [s for s in normalized if s != base]

    final = [base] + normalized[:2]

    logger.info("Final biomedical terms: %s", final)
    logger.info("=== EBI OLS SYNONYM EXPANSION END ===")

    return final
