# app/agents/web_intelligence.py

from typing import List, Dict, Any
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import time

from ddgs import DDGS  # pip install ddgs

router = APIRouter()

# ======================================================
# DOMAIN CLASSIFICATION (TYPE-BASED, NO TIERS)
# ======================================================

DOMAIN_SIGNAL_MAP = {
    # Regulatory / guidelines
    "fda.gov": "REGULATORY",
    "ema.europa.eu": "REGULATORY",
    "who.int": "REGULATORY",

    # Scholarly / journals
    "nih.gov": "SCHOLARLY",
    "ncbi.nlm.nih.gov": "SCHOLARLY",
    "pubmed.ncbi.nlm.nih.gov": "SCHOLARLY",
    "nejm.org": "SCHOLARLY",
    "thelancet.com": "SCHOLARLY",
    "bmj.com": "SCHOLARLY",
    "nature.com": "SCHOLARLY",
    "science.org": "SCHOLARLY",
    "sciencedirect.com": "SCHOLARLY",
    "wiley.com": "SCHOLARLY",
    "springer.com": "SCHOLARLY",
    "frontiersin.org": "SCHOLARLY",

    # Preprints / pipeline
    "clinicaltrials.gov": "PIPELINE",
    "medrxiv.org": "PIPELINE",
    "biorxiv.org": "PIPELINE",

    # Industry / news
    "reuters.com": "NEWS",
    "statnews.com": "NEWS",
    "endpts.com": "NEWS",
    "fiercepharma.com": "NEWS",
    "fiercebiotech.com": "NEWS",
    "biopharmadive.com": "NEWS",
    "pharmaphorum.com": "NEWS",
}

BLOCKED_KEYWORDS = {
    "forum", "reddit", "facebook", "twitter", "x.com",
    "patient", "donation", "support", "blog", "community"
}

REQUEST_SLEEP_SECONDS = 1.0

# ======================================================
# REQUEST MODEL (LOCKED CONTRACT)
# ======================================================

class WebIntelligenceRequest(BaseModel):
    drug: str = Field(default="")
    conditions: List[str] = Field(default_factory=list)
    max_results: int = Field(default=5, ge=5, le=30)

# ======================================================
# UTILITIES
# ======================================================

def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _is_blocked(url: str) -> bool:
    u = url.lower()
    return any(b in u for b in BLOCKED_KEYWORDS)

def _is_english(text: str) -> bool:
    if not text:
        return False
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return non_ascii / max(len(text), 1) < 0.05

def _classify_signal(domain: str) -> str:
    for d, t in DOMAIN_SIGNAL_MAP.items():
        if domain.endswith(d):
            return t
    return "UNKNOWN"

def _confidence_from_type(signal_type: str) -> str:
    if signal_type in {"REGULATORY", "SCHOLARLY"}:
        return "HIGH"
    if signal_type == "PIPELINE":
        return "MEDIUM"
    return "LOW"

# ======================================================
# QUERY VARIANT GENERATION (PURELY SYNTACTIC)
# ======================================================

def build_query_variants(drug: str, condition: str) -> List[str]:
    variants = []

    if drug and condition:
        variants.extend([
            f"\"{drug}\" \"{condition}\"",
            f"{drug} {condition}",
        ])
        cond_tokens = condition.split()
        if len(cond_tokens) > 1:
            variants.append(f"{drug} {cond_tokens[-1]}")

    elif drug:
        variants.append(f"\"{drug}\"")

    elif condition:
        variants.append(f"\"{condition}\"")

    return list(dict.fromkeys(variants))

# ======================================================
# CORE SEARCH
# ======================================================

def search_web(
    drug: str,
    conditions: List[str],
    max_results: int
) -> List[Dict[str, Any]]:

    collected: Dict[str, Dict[str, Any]] = {}

    # resolve pairs (MATCHES CLINICAL + LITERATURE LOGIC)
    if drug and conditions:
        pairs = [(drug, c) for c in conditions]
    elif drug:
        pairs = [(drug, "")]
    elif conditions:
        pairs = [("", c) for c in conditions]
    else:
        return []

    with DDGS() as ddg:
        for drug_term, condition_term in pairs:
            queries = build_query_variants(drug_term, condition_term)

            for q in queries:
                time.sleep(REQUEST_SLEEP_SECONDS)

                results = ddg.text(
                    q,
                    max_results=10,
                    safesearch="moderate",
                    region="wt-wt"
                )

                for r in results:
                    url = r.get("href") or ""
                    title = r.get("title") or ""
                    snippet = r.get("body") or ""

                    if not url or _is_blocked(url):
                        continue

                    if not _is_english(title + " " + snippet):
                        continue

                    if url in collected:
                        continue

                    domain = _extract_domain(url)
                    signal_type = _classify_signal(domain)

                    collected[url] = {
                        "title": title.strip(),
                        "snippet": snippet.strip(),
                        "source_domain": domain,
                        "url": url,
                        "signal_type": signal_type,
                        "confidence": _confidence_from_type(signal_type),
                    }

                    if len(collected) >= max_results:
                        return list(collected.values())

    return list(collected.values())

# ======================================================
# ENDPOINT — PLAIN TEXT OUTPUT
# ======================================================

@router.post("/web_intelligence", tags=["web"])
def web_intelligence_endpoint(req: WebIntelligenceRequest):

    drug = req.drug.strip()
    conditions = [c.strip() for c in req.conditions if c.strip()]

    if not drug and not conditions:
        return Response(
            content=(
                "WEB INTELLIGENCE SIGNALS\n\n"
                "No drug or condition provided.\n"
                "At least one of drug or condition must be specified."
            ),
            media_type="text/plain",
        )

    signals = search_web(
        drug=drug,
        conditions=conditions,
        max_results=req.max_results
    )

    lines: List[str] = []

    lines.append("WEB INTELLIGENCE SIGNALS\n")
    lines.append(f"Drug       : {drug or 'N/A'}")
    lines.append(
        f"Conditions : {', '.join(conditions) if conditions else 'N/A'}\n"
    )
    lines.append(f"Total signals found : {len(signals)}\n")

    if not signals:
        lines.append(
            "No relevant web intelligence signals were found.\n"
            "Signals are non-clinical and absence does not imply lack of evidence."
        )
        return Response(content="\n".join(lines), media_type="text/plain")

    for idx, s in enumerate(signals, start=1):
        lines.append(f"{idx}. {s['title']}")
        lines.append(f"   Source     : {s['source_domain']}")
        lines.append(f"   Type       : {s['signal_type']}")
        lines.append(f"   Confidence : {s['confidence']}")
        lines.append(f"   URL        : {s['url']}\n")
        lines.append("   Snippet:")
        lines.append(s["snippet"] or "   Snippet not available.")
        lines.append("\n" + "-" * 100)

    lines.append(
        "\nNOTE:\n"
        "Web intelligence signals are non-validated, non-clinical, English-only, "
        "and contextual. They must not be treated as evidence. But only as sign of interest."
    )

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
    )