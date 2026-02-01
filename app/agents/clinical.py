from typing import List, Dict
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from app.services.clinicaltrials import client, TrialHit

logger = logging.getLogger("clinical-agent")
router = APIRouter()


# ======================================================
# INPUT MODEL (FIXED, EMPTY FIELDS ALLOWED)
# ======================================================

class ClinicalRequest(BaseModel):
    drug: str = ""
    conditions: List[str] = Field(default_factory=list, max_items=5)
    max_results: int = Field(default=5, ge=5, le=30)


# ======================================================
# SCORING (UNCHANGED)
# ======================================================

def score_trial(t: TrialHit) -> float:
    score = 0.0

    phase_weight = {
        "PHASE4": 5,
        "PHASE3": 4,
        "PHASE2": 3,
        "PHASE1": 2,
        "EARLY_PHASE1": 1.5
    }

    score += phase_weight.get((t.phase or "").upper(), 1)

    if "recruit" in t.status.lower():
        score += 2

    if t.start_year:
        age = datetime.now().year - t.start_year
        score += max(0, 3 - age * 0.3)

    score += min((t.locations_count or 0) / 10, 2)

    return round(score, 2)


# ======================================================
# RETRIEVAL — STRICT & CORRECTED
# ======================================================

def retrieve_trials(
    drug: str,
    conditions: List[str],
    limit: int
) -> List[TrialHit]:

    pool: Dict[str, TrialHit] = {}

    # 🔒 NORMALIZE CONDITIONS (CRITICAL FIX)
    clean_conditions = [c.strip() for c in conditions if c and c.strip()]

    # CASE 1: drug + valid conditions
    if drug and clean_conditions:
        for cond in clean_conditions:
            query = f"{drug} AND {cond}"
            logger.info("ClinicalTrials.gov query → %s", query)
            for t in client.search_studies(query, limit * 3):
                pool[t.nct_id] = t

    # CASE 2: drug only
    elif drug:
        logger.info("ClinicalTrials.gov query → %s", drug)
        for t in client.search_studies(drug, limit * 5):
            pool[t.nct_id] = t

    # CASE 3: conditions only
    elif clean_conditions:
        for cond in clean_conditions:
            logger.info("ClinicalTrials.gov query → %s", cond)
            for t in client.search_studies(cond, limit * 5):
                pool[t.nct_id] = t

    return list(pool.values())


# ======================================================
# SIGNALS (UNCHANGED)
# ======================================================

def compute_signals(trials: List[TrialHit]) -> dict:
    phase_dist: Dict[str, int] = {}
    recruiting = 0
    latest_year = None

    for t in trials:
        phase = t.phase or "UNKNOWN"
        phase_dist[phase] = phase_dist.get(phase, 0) + 1

        if "recruit" in t.status.lower():
            recruiting += 1

        if t.start_year:
            latest_year = max(latest_year or t.start_year, t.start_year)

    return {
        "total_trials": len(trials),
        "phase_distribution": phase_dist,
        "recruiting_trials": recruiting,
        "latest_start_year": latest_year,
    }


# ======================================================
# ENDPOINT — PLAIN TEXT
# ======================================================

@router.post("/clinical")
def clinical_endpoint(req: ClinicalRequest):

    try:
        trials = retrieve_trials(
            req.drug,
            req.conditions,
            req.max_results
        )

        clean_conditions = [c.strip() for c in req.conditions if c and c.strip()]

        if not trials:
            text = (
                "CLINICAL TRIAL SIGNALS\n"
                f"Drug      : {req.drug}\n"
                f"Conditions: {', '.join(clean_conditions) or 'N/A'}\n\n"
                "No registered clinical trials found.\n"
                "This suggests a lack of formal clinical investigation.\n"
            )
            return Response(content=text, media_type="text/plain")

        for t in trials:
            t.score = score_trial(t)

        trials.sort(key=lambda x: x.score, reverse=True)
        final_trials = trials[:req.max_results]

        signals = compute_signals(final_trials)

        lines = []
        lines.append("CLINICAL TRIAL SIGNALS")
        lines.append(f"Drug      : {req.drug}")
        lines.append(f"Conditions: {', '.join(clean_conditions) or 'N/A'}\n")

        lines.append(f"Total matching trials      : {signals['total_trials']}")
        lines.append(f"Recruiting trials          : {signals['recruiting_trials']}")
        lines.append(
            f"Latest trial start year    : {signals['latest_start_year'] or 'N/A'}"
        )
        lines.append("Phase distribution:")
        for p, c in signals["phase_distribution"].items():
            lines.append(f"  - {p} : {c}")

        lines.append("\nTOP CLINICAL TRIALS (by score)\n")

        rank = 1
        for t in final_trials:
            lines.append(f"{rank}. {t.title}")
            lines.append(f"   Phase    : {t.phase or 'UNKNOWN'}")
            lines.append(f"   Status   : {t.status}")
            lines.append(f"   Sponsor  : {t.sponsor}")
            lines.append(f"   NCT ID   : {t.nct_id}")
            lines.append(f"   URL      : {t.url}\n")
            rank += 1

        return Response(
            content="\n".join(lines),
            media_type="text/plain"
        )

    except Exception:
        logger.exception("Clinical agent failed")
        raise HTTPException(
            status_code=500,
            detail="Clinical agent failed internally"
        )
