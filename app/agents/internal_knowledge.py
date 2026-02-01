from fastapi import APIRouter, Response, Depends
from pydantic import BaseModel
from typing import List

from app.services.internal_knowledge_service import (
    retrieve_candidate_documents,
)
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthUser

router = APIRouter()


# ======================================================
# REQUEST MODEL (ALIGNED)
# ======================================================

class InternalKnowledgeRequest(BaseModel):
    drug: str = ""
    conditions: List[str] = []
    use_llm_extraction: bool = True  # intentionally inert


# ======================================================
# ENDPOINT — PLAIN TEXT
# ======================================================

@router.post("/internal-knowledge", tags=["internal_knowledge"])
async def query_internal_knowledge(
    req: InternalKnowledgeRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    drug = req.drug.strip()
    conditions = [c.strip() for c in req.conditions if c.strip()]

    if not drug and not conditions:
        return Response(
            content=(
                "INTERNAL KNOWLEDGE SIGNALS\n\n"
                "No drug or condition provided.\n"
                "At least one must be specified."
            ),
            media_type="text/plain",
        )

    all_results = {}
    query_pairs = []

    if drug and conditions:
        query_pairs = [(drug, c) for c in conditions]
        mode = "DRUG_AND_CONDITION"
    elif drug:
        query_pairs = [(drug, None)]
        mode = "DRUG_ONLY"
    else:
        query_pairs = [(None, c) for c in conditions]
        mode = "CONDITION_ONLY"

    # 🔐 REAL COMPANY ID FROM AUTH
    company_id = current_user.company_id

    for d, c in query_pairs:
        docs = retrieve_candidate_documents(
            company_id=company_id,
            drug=d,
            condition=c
        )
        for doc in docs:
            all_results[doc["document_id"]] = doc

    if not all_results:
        return Response(
            content=(
                "INTERNAL KNOWLEDGE SIGNALS\n\n"
                f"Query mode : {mode}\n"
                f"Drug       : {drug or 'N/A'}\n"
                f"Conditions : {', '.join(conditions) or 'N/A'}\n\n"
                "No internal knowledge records matched."
            ),
            media_type="text/plain",
        )

    # -----------------------------
    # PLAIN TEXT OUTPUT
    # -----------------------------

    lines = []
    lines.append("INTERNAL KNOWLEDGE SIGNALS\n")
    lines.append(f"Query mode : {mode}")
    lines.append(f"Drug       : {drug or 'N/A'}")
    lines.append(f"Conditions : {', '.join(conditions) or 'N/A'}\n")
    lines.append(f"Total internal records : {len(all_results)}\n")

    for idx, doc in enumerate(all_results.values(), start=1):
        excerpt = doc["raw_text"][:800].strip()

        lines.append(f"{idx}. Document ID : {doc['document_id']}")
        lines.append(f"   Type        : {doc['document_type']}")
        lines.append(f"   Confidence  : {doc['confidence'].upper()}")
        lines.append("   Excerpt:")
        lines.append(excerpt)
        lines.append("\n" + "-" * 100)

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
    )
