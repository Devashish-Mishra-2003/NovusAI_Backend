from typing import List, Dict, Optional
import io
import re

from app.services.supabase_client import supabase
from PyPDF2 import PdfReader


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception:
        # Corrupt / encrypted / image-only PDF
        return ""


def _extract_text_from_txt(txt_bytes: bytes) -> str:
    return txt_bytes.decode("utf-8", errors="ignore")


def _load_documents(company_id: int) -> List[Dict]:
    folder = str(company_id)

    result = supabase.storage.from_("company_docs").list(path=folder)

    documents: List[Dict] = []

    for obj in result:
        name = obj["name"]

        if not (name.endswith(".txt") or name.endswith(".pdf")):
            continue

        path = f"{folder}/{name}"

        file_bytes = supabase.storage.from_("company_docs").download(path)

        if name.endswith(".pdf"):
            text = _extract_text_from_pdf(file_bytes)
            doc_type = "pdf"
        else:
            text = _extract_text_from_txt(file_bytes)
            doc_type = "txt"

        documents.append({
            "document_id": path,
            "document_type": doc_type,
            "raw_text": text,
        })

    return documents


def _basic_match(
    text: str,
    drug: Optional[str],
    condition: Optional[str]
) -> bool:
    t = _normalize(text)

    if drug and drug.lower() not in t:
        return False

    if condition and condition.lower() not in t:
        return False

    return True


def retrieve_candidate_documents(
    company_id: int,
    drug: Optional[str],
    condition: Optional[str]
) -> List[Dict]:

    documents = _load_documents(company_id)
    results: List[Dict] = []

    for doc in documents:
        if _basic_match(doc["raw_text"], drug, condition):
            results.append({
                **doc,
                "confidence": "high"
            })

    return results
