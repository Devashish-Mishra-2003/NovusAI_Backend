# app/services/orchestration_llm.py

"""
THIS MODULE IS INTENTIONALLY DISABLED.

All semantic reasoning (entity extraction, intent classification,
synonym expansion) has been moved to the SYNTHESIS layer.

Orchestration MUST NOT call any LLMs.
This file exists only to avoid accidental imports breaking.
"""

import logging

logger = logging.getLogger("orchestration-llm")

def extract_entities(*args, **kwargs):
    raise RuntimeError(
        "extract_entities() is disabled. "
        "Entity extraction must happen in synthesis."
    )

def classify_intent_and_facets(*args, **kwargs):
    raise RuntimeError(
        "classify_intent_and_facets() is disabled. "
        "Intent classification must happen in synthesis."
    )
