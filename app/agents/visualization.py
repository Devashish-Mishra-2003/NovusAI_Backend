# app/agents/visualization.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import logging
import re
from datetime import datetime

logger = logging.getLogger("visualization")
router = APIRouter()

# ======================================================
# REQUEST / RESPONSE MODELS
# ======================================================

class VisualizationRequest(BaseModel):
    market_data: str
    clinical_data: str


class VisualizationResponse(BaseModel):
    market: Optional[Dict[str, Any]] = None
    clinical: Optional[Dict[str, Any]] = None


# ======================================================
# GENERIC HELPERS
# ======================================================

def extract_float(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    try:
        val = float(match.group(1))
        return round(val, 2)
    except Exception:
        return None


def generate_market_timeline(
    start_value: float,
    cagr: float,
    start_year: int,
    end_year: int,
    target_2030: Optional[float] = None
) -> List[Dict[str, float]]:
    timeline = []
    current = start_value
    for year in range(start_year, end_year + 1):
        if year == 2030 and target_2030 is not None:
            value = target_2030
        else:
            value = round(current, 2)
        timeline.append({"year": year, "value": value})
        current *= (1 + cagr / 100)
    return timeline


# ======================================================
# MARKET PARSER — FIXED
# ======================================================

def parse_market(text: str) -> Optional[Dict[str, Any]]:
    if not text or "market overview" not in text.lower():
        return None

    # Extract with exact patterns from your agent
    current = extract_float(r"current market size.*?[\$]?([\d\.]+)", text)
    forecast = extract_float(r"forecast 2030 market size.*?[\$]?([\d\.]+)", text)
    cagr = extract_float(r"cagr.*?([\d\.]+)", text)
    population = extract_float(r"patient population.*?([\d\.]+)", text)
    treated_pct = extract_float(r"treated population.*?([\d\.]+)", text)

    if not current:
        return None

    year_now = datetime.now().year
    end_year = 2030

    # Force timeline to end at exact forecast if available
    target_2030 = forecast

    base = generate_market_timeline(current, cagr or 0, year_now, end_year, target_2030=target_2030)

    # Bands ±2%
    upper = generate_market_timeline(current, (cagr or 0) + 2, year_now, end_year, target_2030=target_2030 * 1.1 if target_2030 else None)
    lower = generate_market_timeline(current, max((cagr or 0) - 2, 0), year_now, end_year, target_2030=target_2030 * 0.9 if target_2030 else None)

    market_block: Dict[str, Any] = {
        "current_usd_bn": current,
        "forecast_2030_usd_bn": target_2030 or round(base[-1]["value"], 2),
        "cagr_percent": cagr or 0,
        "timeline": base,
        "bands": {
            "upper": upper,
            "lower": lower
        }
    }

    if population is not None and treated_pct is not None:
        treated_pop = round(population * treated_pct / 100, 2)
        untreated_pop = round(population - treated_pop, 2)
        market_block["patient_split"] = {
            "total_population_m": population,
            "treated_population_m": treated_pop,
            "untreated_population_m": untreated_pop,
            "treated_percent": treated_pct
        }

    return market_block


# ======================================================
# CLINICAL PARSER — ALREADY ROBUST (keep your fixed version)
# ======================================================

def parse_clinical(text: str) -> Optional[Dict[str, Any]]:
    if not text or not isinstance(text, str):
        return None

    if any(phrase in text.lower() for phrase in [
        "no registered clinical trials",
        "no matching trials",
        "total matching trials : 0",
        "no clinical trial signals"
    ]):
        return None

    phase_counts = {
        "PHASE1": 0,
        "PHASE2": 0,
        "PHASE3": 0,
        "PHASE4": 0,
        "OTHER": 0
    }

    pattern = re.compile(r"PHASE\s*(\d)\s*[:\-]?\s*(\d+)", re.IGNORECASE)

    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            phase_num = f"PHASE{match.group(1)}"
            count = int(match.group(2))
            if phase_num in phase_counts:
                phase_counts[phase_num] = count
            else:
                phase_counts["OTHER"] += count

    total = sum(phase_counts.values())
    if total == 0:
        return None

    return {
        "total_trials": total,
        "by_phase": phase_counts
    }


# ======================================================
# ENDPOINT
# ======================================================

@router.post("/visualize", response_model=VisualizationResponse)
def visualize(req: VisualizationRequest):
    try:
        market_block = parse_market(req.market_data)
        clinical_block = parse_clinical(req.clinical_data)

        if not market_block and not clinical_block:
            raise HTTPException(status_code=400, detail="No visualizable data found")

        return VisualizationResponse(
            market=market_block,
            clinical=clinical_block
        )

    except Exception:
        logger.exception("Visualization agent failed")
        raise HTTPException(status_code=500, detail="Visualization agent failed internally")