# app/services/market_mock.py

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, Any, Optional, List

CURRENT_DIR = Path(__file__).resolve().parent
APP_DIR = CURRENT_DIR.parent

PAIR_PATH = APP_DIR / "mockdata" / "market_mock.json"
DRUG_ONLY_PATH = APP_DIR / "mockdata" / "market_drug_only.json"
CONDITION_ONLY_PATH = APP_DIR / "mockdata" / "market_condition_only.json"


class MarketMockError(Exception):
    pass


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.lower()
    text = re.sub(r"[-–—_/]", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _load(path: Path) -> List[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise MarketMockError(f"Failed to load {path}: {e}") from e


PAIR_DATA = _load(PAIR_PATH)
DRUG_ONLY_DATA = _load(DRUG_ONLY_PATH)
CONDITION_ONLY_DATA = _load(CONDITION_ONLY_PATH)


# --------------------------------------------------
# LOOKUPS
# --------------------------------------------------

def lookup_pair(drug: str, condition: str) -> Optional[Dict[str, Any]]:
    drug = _norm(drug)
    condition = _norm(condition)

    for row in PAIR_DATA:
        if _norm(row["drug_name"]) == drug and _norm(row["condition"]) == condition:
            return row
    return None


def lookup_drug_only(drug: str) -> Optional[Dict[str, Any]]:
    drug = _norm(drug)

    for row in DRUG_ONLY_DATA:
        if _norm(row["drug_name"]) == drug:
            return row
    return None


def lookup_condition_only(condition: str) -> Optional[Dict[str, Any]]:
    condition = _norm(condition)

    for row in CONDITION_ONLY_DATA:
        if _norm(row["condition"]) == condition:
            return row
    return None
