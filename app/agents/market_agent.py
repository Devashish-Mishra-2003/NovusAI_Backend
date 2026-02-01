# app/agents/market_agent.py

from typing import List, Optional
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
import re
import unicodedata

from app.services.market_mock import (
    lookup_pair,
    lookup_drug_only,
    lookup_condition_only,
)

router = APIRouter()


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[-–—_/]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --------------------------------------------------
# INPUT MODEL (FINAL)
# --------------------------------------------------

class MarketRequest(BaseModel):
    drug: str = Field(default="")
    conditions: List[str] = Field(default_factory=list, max_items=5)


# --------------------------------------------------
# ENDPOINT — PLAIN TEXT
# --------------------------------------------------

@router.post("/market")
async def market_endpoint(req: MarketRequest):

    drug = req.drug.strip()
    conditions = [c.strip() for c in req.conditions if c.strip()]

    # ---------------------------
    # MODE RESOLUTION
    # ---------------------------

    if drug and conditions:
        mode = "DRUG_AND_CONDITION"
    elif drug:
        mode = "DRUG_ONLY"
    elif conditions:
        mode = "CONDITION_ONLY"
    else:
        return Response(
            content=(
                "MARKET SIGNALS\n\n"
                "No drug or condition provided.\n"
            ),
            media_type="text/plain",
        )

    blocks: List[str] = []

    # ---------------------------
    # PAIR MODE
    # ---------------------------

    if mode == "DRUG_AND_CONDITION":
        for condition in conditions:
            match = lookup_pair(drug, condition)
            if not match:
                continue
            blocks.append(_render_block("DRUG_AND_CONDITION", drug, condition, match))

    # ---------------------------
    # DRUG ONLY MODE
    # ---------------------------

    elif mode == "DRUG_ONLY":
        match = lookup_drug_only(drug)
        if match:
            blocks.append(_render_block("DRUG_ONLY", drug, None, match))

    # ---------------------------
    # CONDITION ONLY MODE
    # ---------------------------

    elif mode == "CONDITION_ONLY":
        for condition in conditions:
            match = lookup_condition_only(condition)
            if match:
                blocks.append(_render_block("CONDITION_ONLY", None, condition, match))

    if not blocks:
        return Response(
            content=(
                "MARKET SIGNALS\n\n"
                f"Query mode : {mode}\n"
                "No commercial market coverage found.\n"
            ),
            media_type="text/plain",
        )

    return Response(
        content=("\n\n" + "-" * 100 + "\n\n").join(blocks),
        media_type="text/plain",
    )


# --------------------------------------------------
# RENDERING
# --------------------------------------------------

def _render_block(mode: str, drug: Optional[str], condition: Optional[str], m: dict) -> str:
    lines = []

    lines.append("MARKET SIGNALS")
    lines.append(f"Query mode : {mode}")
    if drug:
        lines.append(f"Drug       : {drug}")
    if condition:
        lines.append(f"Condition  : {condition}")
    lines.append("")

    lines.append("Market overview:")
    lines.append(f"  - Current market size (USD bn)      : {m['global_market_size_usd_bn']}")
    lines.append(f"  - Forecast 2030 market size (USD bn): {m['forecast_market_size_usd_bn_2030']}")
    lines.append(f"  - CAGR (%)                          : {m['cagr_percent']}")
    lines.append(f"  - Patient population (millions)     : {m['patient_population_millions']}")
    lines.append(f"  - Treated population (%)            : {m['treated_population_percent']}\n")

    lines.append("Competitive landscape:")
    lines.append(f"  - Number of competitors : {m['number_of_competitors']}")
    lines.append(f"  - Branded vs generic mix : {m['branded_vs_generic_mix']}")
    lines.append(f"  - Key competitor classes : {', '.join(m['key_competitor_classes'])}\n")

    if m.get("commercial_signals"):
        lines.append("Commercial signals:")
        for s in m["commercial_signals"]:
            lines.append(f"  - {s}")
        lines.append("")

    if m.get("risks"):
        lines.append("Risks:")
        for r in m["risks"]:
            lines.append(f"  - {r}")
        lines.append("")

    return "\n".join(lines)
