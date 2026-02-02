# app/pre_synthesis/groq_interpreter.py

import re
import logging
from typing import Dict, List

from openai import OpenAI
from app.pre_synthesis.condition_synonyms import expand_condition
from app.config import settings

logger = logging.getLogger("groq-interpreter")

client = OpenAI(
    base_url=settings.GROQ_BASE_URL,
    api_key=settings.GROQ_API_KEY,
)

MODEL_NAME = settings.MODEL_NAME


SYSTEM_PROMPT = """
You are a biomedical query interpreter.

Your task is to extract:
1) the primary drug (if any),
2) the primary disease (if any),
3) the user intent.

OUTPUT FORMAT (EXACTLY 3 LINES):
DRUG: <comma-separated drug names or NONE>
CONDITION: <condition name or NONE>
INTENT: <ONE OF THE VALUES BELOW>

ALLOWED INTENT VALUES:
- CLINICAL
- COMMERCIAL
- INTERNAL
- FULL_OPPORTUNITY
- GENERAL
""".strip()

_BRACKET_RE = re.compile(r"\s*\(.*?\)\s*")


def _normalize_text(value: str) -> str:
    value = _BRACKET_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _parse_llm_output(text: str) -> Dict[str, object]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("DRUG:", "CONDITION:", "INTENT:")):
            lines.append(line)

    if len(lines) != 3:
        raise ValueError(f"Invalid LLM output: {lines}")

    def extract(prefix: str, line: str) -> str:
        return line[len(prefix):].strip()

    raw_drug = extract("DRUG:", lines[0])
    drugs = [] if raw_drug.upper() == "NONE" else [
        _normalize_text(d.strip()) for d in raw_drug.split(",") if d.strip()
    ]

    raw_condition = extract("CONDITION:", lines[1])
    condition = None if raw_condition.upper() == "NONE" else _normalize_text(raw_condition)

    intent = extract("INTENT:", lines[2]).strip().upper()

    return {"drug": drugs, "condition": condition, "intent": intent}


def interpret_query(query: str) -> Dict[str, object]:
    if not query.strip():
        return {"drug": [], "conditions": [], "intent": "GENERAL"}

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        temperature=0.0,
        max_tokens=60,
    )

    parsed = _parse_llm_output(response.choices[0].message.content.strip())
    conditions = expand_condition(parsed["condition"]) if parsed["condition"] else []

    return {
        "drug": parsed["drug"],
        "conditions": conditions,
        "intent": parsed["intent"],
    }
