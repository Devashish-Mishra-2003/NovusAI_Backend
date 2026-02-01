# app/agents/literature.py

from typing import Optional, Dict, Any, List, Literal
import math
import logging

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.services.pubmed_literature import (
    build_pubmed_query,
    search_pubmed_ids,
    fetch_pubmed_summaries,
    fetch_pubmed_abstracts,
    fetch_mesh_terms,
    infer_population_flag_from_mesh_and_text,
)
from app.services.icite_client import fetch_icite_metrics

logger = logging.getLogger("literature-agent")
router = APIRouter()

Confidence = Literal["DIRECT_EVIDENCE", "NO_RELEVANT_LITERATURE"]

# -------------------------------------------------
# REQUEST MODEL (FIXED)
# -------------------------------------------------

class LiteratureRequest(BaseModel):
    drug: str = ""
    conditions: List[str] = Field(default_factory=list, max_items=5)
    include_veterinary: bool = Field(default=False)
    max_results: int = Field(default=5, ge=5, le=50)

# -------------------------------------------------
# INTERNAL HELPERS (UNCHANGED)
# -------------------------------------------------

def _classify_study_design(article_types: List[str]) -> str:
    types = [t.lower() for t in article_types]
    if any("meta-analysis" in t for t in types):
        return "META_ANALYSIS"
    if any("systematic review" in t for t in types):
        return "SYSTEMATIC_REVIEW"
    if any("randomized" in t or "clinical trial" in t for t in types):
        return "RCT_OR_TRIAL"
    if any("cohort" in t or "case-control" in t or "observational" in t for t in types):
        return "OBSERVATIONAL"
    if any("case report" in t for t in types):
        return "CASE_REPORT"
    return "OTHER"

def _study_design_weight(design: str) -> float:
    return {
        "META_ANALYSIS": 1.0,
        "SYSTEMATIC_REVIEW": 0.95,
        "RCT_OR_TRIAL": 0.9,
        "OBSERVATIONAL": 0.7,
        "CASE_REPORT": 0.4,
        "OTHER": 0.5,
    }.get(design, 0.5)

def _population_weight(flag: str) -> float:
    return {
        "HUMAN": 1.0,
        "ANIMAL_PRECLINICAL": 0.6,
        "VETERINARY_ONLY": 0.1,
        "UNKNOWN": 0.4,
    }.get(flag, 0.4)

def _year_weight(year: Optional[int], current_year: int = 2025) -> float:
    if not year:
        return 0.4
    age = max(0, current_year - year)
    return max(0.3, math.exp(-age / 15.0))

def _citation_weight(citations: int, rcr: float) -> float:
    base = math.log1p(max(0, citations)) / math.log(101)
    rcr_component = min(2.0, max(0.0, rcr)) / 4.0
    return min(1.0, base + rcr_component)

def _compute_score(year, study_design, population_flag, citation_count, rcr) -> float:
    return round(
        0.35 * _year_weight(year)
        + 0.25 * _study_design_weight(study_design)
        + 0.20 * _population_weight(population_flag)
        + 0.20 * _citation_weight(citation_count, rcr),
        4,
    )

# -------------------------------------------------
# ROUTER ENDPOINT — PLAIN TEXT OUTPUT
# -------------------------------------------------

@router.post("/literature", tags=["literature"])
def literature_endpoint(req: LiteratureRequest):

    drug = req.drug.strip()
    conditions = [c.strip() for c in req.conditions if c.strip()]

    # -----------------------------
    # QUERY MODE RESOLUTION (FIXED)
    # -----------------------------
    if drug and conditions:
        mode = "DRUG_AND_CONDITION"
    elif drug:
        mode = "DRUG_ONLY"
    elif conditions:
        mode = "CONDITION_ONLY"
    else:
        return Response(
            content=(
                "LITERATURE EVIDENCE (PUBMED)\n\n"
                "No drug or condition provided.\n"
                "At least one of drug or condition must be specified."
            ),
            media_type="text/plain",
        )

    # -----------------------------
    # BUILD QUERY (FIXED)
    # -----------------------------
    query = build_pubmed_query(
        drug=drug or None,
        conditions=conditions,
        mode=mode,
    )

    pmids = search_pubmed_ids(query, retmax=req.max_results, sort="pub+date")

    if not pmids:
        return Response(
            content=(
                "LITERATURE EVIDENCE (PUBMED)\n\n"
                f"Query mode : {mode}\n"
                f"Drug       : {drug or 'N/A'}\n"
                f"Conditions : {', '.join(conditions) or 'N/A'}\n\n"
                "No relevant PubMed literature found where the query terms "
                "appear in the title or abstract.\n"
                "This suggests a lack of direct published evidence."
            ),
            media_type="text/plain",
        )

    summaries = fetch_pubmed_summaries(pmids)
    abstracts = fetch_pubmed_abstracts(pmids)
    mesh_terms = fetch_mesh_terms(pmids)
    icite = fetch_icite_metrics(pmids)

    papers: List[Dict[str, Any]] = []

    for s in summaries:
        pmid = s["pmid"]
        abstract_text = abstracts.get(pmid, "")
        mesh = mesh_terms.get(pmid, [])

        population_flag = infer_population_flag_from_mesh_and_text(mesh, abstract_text)
        if population_flag == "VETERINARY_ONLY" and not req.include_veterinary:
            continue

        metrics = icite.get(pmid, {})
        score = _compute_score(
            s["publication_year"],
            _classify_study_design(s["article_types"]),
            population_flag,
            int(metrics.get("citation_count", 0)),
            float(metrics.get("relative_citation_ratio", 0.0)),
        )

        papers.append({
            "pmid": pmid,
            "title": s["title"],
            "journal": s["journal"],
            "publication_year": s["publication_year"],
            "study_design": _classify_study_design(s["article_types"]),
            "population_flag": population_flag,
            "abstract_snippet": abstract_text[:600],
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "score": score,
        })

    papers.sort(key=lambda p: (p["score"], p.get("publication_year") or 0), reverse=True)

    # -----------------------------
    # PLAIN TEXT RESPONSE
    # -----------------------------

    lines = [
        "LITERATURE EVIDENCE (PUBMED)\n",
        f"Query mode : {mode}",
        f"Drug       : {drug or 'N/A'}",
        f"Conditions : {', '.join(conditions) or 'N/A'}\n",
        f"Total relevant papers : {len(papers)}\n",
        "TOP PUBMED EVIDENCE\n",
    ]

    for idx, p in enumerate(papers, start=1):
        lines.extend([
            f"{idx}. {p['title']}",
            f"   Journal     : {p['journal']}",
            f"   Year        : {p['publication_year'] or 'N/A'}",
            f"   Study type  : {p['study_design']}",
            f"   Population  : {p['population_flag']}",
            f"   PMID        : {p['pmid']}",
            f"   URL         : {p['pubmed_url']}\n",
            "   Abstract:",
            p["abstract_snippet"] or "   Abstract not available.",
            "\n" + "-" * 100,
        ])

    return Response("\n".join(lines), media_type="text/plain")
