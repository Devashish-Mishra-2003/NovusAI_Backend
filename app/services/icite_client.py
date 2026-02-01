# app/services/icite_client.py

from typing import List, Dict
import requests

ICITE_BASE = "https://icite.od.nih.gov/api"

def fetch_icite_metrics(pmids: List[str]) -> Dict[str, Dict]:
    if not pmids:
        return {}

    params = {"pmids": ",".join(pmids)}
    resp = requests.get(f"{ICITE_BASE}/pubs", params=params, timeout=15)
    resp.raise_for_status()

    out: Dict[str, Dict] = {}
    for row in resp.json().get("data", []):
        pmid = str(row.get("pmid"))
        if pmid:
            out[pmid] = {
                "citation_count": int(row.get("citations", 0) or 0),
                "relative_citation_ratio": float(row.get("relative_citation_ratio", 0.0) or 0.0),
            }

    return out
