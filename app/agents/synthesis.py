# app/agents/synthesis.py

from fastapi import APIRouter, HTTPException, Depends, Request
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthUser # ← Added Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import json  # ← Added for visualizations_json

import httpx
import logging
import time

from app.services.conversation_state import (
    create_conversation,
    get_conversation,
    update_conversation,
)

from app.pre_synthesis.groq_interpreter import interpret_query
from app.llm.groq_synthesis import run_groq
from app.models.chat import ChatHistory  # ← New import
from app.db import SessionLocal  # ← New import
from app.config import settings

logger = logging.getLogger("synthesis")
router = APIRouter()

BASE_URL = settings.PUBLIC_API_URL.rstrip("/")


# ======================================================
# GENERAL CHAT PROMPT (MINIMAL)
# ======================================================

GENERAL_PROMPT = """
You are NovusAI, a drug repurposing assistant.
Reply concisely in at most 15 words.
""".strip()


# ======================================================
# LOCKED SYSTEM PROMPT FOR SYNTHESIS
# ======================================================

SYSTEM_IDENTITY = """
You are NovusAI, a drug repurposing analysis system delivering precise, evidence-bound scientific reasoning.

Use ONLY the provided EVIDENCE below. Never use external knowledge, internal tags (e.g., [AGENT: CLINICAL]), citations, or meta-commentary.
If a heading has no supporting evidence, skip it entirely. Do not invent content to fill headings.

────────────────────────────────────────
CONTEXT
Drug: {drug}
Condition: {condition}
Intent: {intent}

────────────────────────────────────────
INTENT-BASED EVIDENCE PRIORITIZATION (APPLY STRICTLY)
────────────────────────────────────────
- CLINICAL intent: Evidence limited to Clinical trials and Literature only. Prioritize human clinical data first, then literature findings. 
- COMMERCIAL intent: Prioritize Market overview (size, forecast, unmet need, treated population), then Patent landscape, then Web signals (contextual interest only).
- FULL OPPORTUNITY intent: All agents available. Weight: Clinical (efficacy) > Market (opportunity) > Literature (mechanism) > Patents (protection) > Web (interest).
- INTERNAL intent: Restricted to internal documents only.

────────────────────────────────────────
CORE RULES
────────────────────────────────────────
- Interpret and synthesize analytically — never summarize raw data.
- Clearly state if evidence is absent, weak, indirect, or mixed.
- Never introduce unsupported drugs, outcomes, mechanisms, or certainty.
- Evidence hierarchy: Human clinical > preclinical/animal > mechanistic.
  Later-phase trials > early-phase. Consistent findings > isolated signals.
- Scientific, expert-level tone.

────────────────────────────────────────
STRUCTURED ANSWER FORMAT (MANDATORY — STRICT)
────────────────────────────────────────
Generate headings IN THIS EXACT ORDER and ONLY if the corresponding evidence type is present:

- Include ## Clinical Signals ONLY for CLINICAL or FULL OPPORTUNITY intent with clinical trial data
- Include ## Mechanistic Insights ONLY if biological pathways are described
- Include ## Literature Interpretation ONLY for CLINICAL or FULL OPPORTUNITY intent with literature
- Include ## Market Opportunity ONLY for COMMERCIAL or FULL OPPORTUNITY intent
- Include ## Patent Landscape ONLY for COMMERCIAL or FULL OPPORTUNITY intent
- Include ## Comparative Assessment ONLY when multiple drugs are active
- Always include ## Conclusion and ## Confidence Assessment

Never generate a heading if no matching evidence exists.

## Clinical Signals
[Interpret trial phases, status, and outcomes]

## Mechanistic Insights
[Interpret biological pathways and rationale]

## Literature Interpretation
[Interpret key study implications]

## Market Opportunity
[Interpret size, growth, unmet need, competition, treated population]

## Patent Landscape
[Interpret innovation and protection signals]

## Comparative Assessment
[Only when multiple drugs are active]

## Conclusion
[Direct analytical answer to the user's question]

## Confidence Assessment
Overall confidence: High / Moderate / Low
Basis: One sentence on evidence strength, consistency, and direct relevance.

────────────────────────────────────────
EVIDENCE
{evidence}

────────────────────────────────────────
Respond with depth and precision using the exact heading structure above. Never mention "evidence", "sources", "agents", or internal formatting.
""".strip()


# ======================================================
# COMPARISON PROMPT (KEPT FOR FUTURE USE)
# ======================================================

COMPARISON_PROMPT = """
You are NovusAI, a drug repurposing analysis system.

Your task is to compare the listed drugs for the given condition
based ONLY on the provided evidence.

STRICT RULES:
- Discuss EACH drug separately first.
- Use evidence to interpret implications, not to summarize documents.
- Do NOT infer superiority unless evidence explicitly supports it.
- If evidence is weak or absent for a drug, state that clearly.

CONTEXT
Condition: {condition}

Drugs:
{drug_list}

EVIDENCE (grouped by drug)
{evidence}

ANSWER STRUCTURE:

## <DRUG NAME 1>
1–2 short paragraphs interpreting evidence in context.

## <DRUG NAME 2>
1–2 short paragraphs interpreting evidence in context.

## Comparative Interpretation
- Direct comparison using ONLY stated evidence
- No speculation or ranking without support
""".strip()


# ======================================================
# REQUEST MODEL
# ======================================================

class SynthesisRequest(BaseModel):
    message: str
    conversation_id: str | None = None


# ======================================================
# SYNTHESIS ENDPOINT
# ======================================================

@router.post("/synthesize")
async def synthesize(
    req: SynthesisRequest,
    request: Request,
    current_user: AuthUser = Depends(get_current_user), 
    ):

  # ← Added request: Request
    message = req.message.strip()
    if not message:
        raise HTTPException(400, "Empty message")

    # ---- SAFE CONVERSATION INIT ----

    # 🔥 HYDRATE FROM DB IF RAM STATE IS MISSING
    cid = req.conversation_id or create_conversation()
    state = get_conversation(cid)

    if state is None:
        # Manually create RAM state WITHOUT changing cid
        from app.services.conversation_state import _CONVERSATIONS

        _CONVERSATIONS[cid] = {
            "chat_history": [],
            "orchestration": None,
            "visualization": None,
            "full_summary_text": None,
            "fetched_domains": {
                "clinical": False,
                "literature": False,
                "market": False,
                "patents": False,
                "web": False,
            },
            "active_context": {
                "conditions": [],
                "drug": None,
            },
            "entities_seen": {
                "drugs": set(),
            },
            "mode": "SINGLE",
            "last_intent": None,
            "evidence_cache": {},
            "last_discussed": {
                "drug": None,
                "condition": None,
            },
            "depth": "summary",
            "updated_at": time.time(),
        }

        state = _CONVERSATIONS[cid]

        # 🔁 hydrate from DB
        db = SessionLocal()
        try:
            last_row = (
                db.query(ChatHistory)
                .filter(ChatHistory.conversation_id == cid)
                .order_by(ChatHistory.timestamp.desc())
                .first()
            )

            if last_row:
                update_conversation(
                    cid,
                    active_conditions=last_row.conditions or [],
                    drugs_seen=last_row.active_drugs or [],
                    last_intent=last_row.intent,
                    mode=last_row.mode,
                )
        finally:
            db.close()

        if state is None:
          raise RuntimeError("Conversation state initialization failed")

    # ---- REAL INTENT/DRUG/CONDITION EXTRACTION VIA GROQ ----
    parsed_raw = interpret_query(message)
    drugs: List[str] = parsed_raw["drug"]
    conditions: List[str] = parsed_raw["conditions"]
    intent: str = parsed_raw["intent"]

    # ==================================================
    # ✅ GENERAL INTENT — DIRECT LLM HANDLING
    # ==================================================
    if intent == "GENERAL":
# --- build optional context ---
        context_lines = []

        if state["active_context"].get("conditions"):
            context_lines.append(
                "Condition: " + ", ".join(state["active_context"]["conditions"])
            )

        if state["entities_seen"].get("drugs"):
            context_lines.append(
                "Drug(s): " + ", ".join(state["entities_seen"]["drugs"])
            )

        context_block = ""
        if context_lines:
            context_block = "\nContext:\n" + "\n".join(context_lines)

        prompt = (
            GENERAL_PROMPT
            + context_block
            + "\nUser: "
            + message
            + "\nAnswer:"
        )

        answer = await run_groq(prompt)


        update_conversation(
            cid,
            chat_entry={"user": message, "assistant": answer},
        )

        visualizations: Optional[Dict[str, Any]] = None

        db = SessionLocal()
        try:
            db.add(ChatHistory(
                conversation_id=cid,
                user_id=current_user.user_id,
                question=message,
                answer=answer,
                conditions=None,
                active_drugs=None,
                intent="GENERAL",
                mode="CHAT",
                visualizations_json=json.dumps(visualizations) if visualizations else None,
            ))

            db.commit()
        finally:
            db.close()


        return {
            "type": "conversation",
            "answer": answer,
            "conversation_id": cid,
            "mode": "CHAT",
            "active_drugs": [],
            "condition": None,
            "intent": "GENERAL",
            "visualizations": None,
        }

    # -----------------------------
    # CONDITION LOCK (SMART — ALLOW RELATED/SUPERSET TERMS)
    # -----------------------------
    active_conditions = state["active_context"].get("conditions", [])

    if not active_conditions:
        if conditions:
            active_conditions = conditions
            update_conversation(cid, active_conditions=active_conditions)
    else:
        if conditions:
            # Allow if ANY overlap (partial match) OR new is broader/shorter version
            active_set = set(c.lower() for c in active_conditions)
            new_set = set(c.lower() for c in conditions)

            # Block only if NO overlap at all
            if active_set.isdisjoint(new_set):
                return {
                    "type": "error",
                    "answer": "Condition change is not allowed. Please start a new chat.",
                    "conversation_id": cid,
                }
            # Otherwise, merge and continue (prefer broader set)
            merged = list(active_set.union(new_set))
            if merged != active_conditions:
                active_conditions = merged
                update_conversation(cid, active_conditions=active_conditions)
        # If no new conditions → proceed with existing

    if not active_conditions:
        raise HTTPException(
            400,
            "No condition set. Please specify a condition to proceed."
        )

    # -----------------------------
    # DRUG ACCUMULATION
    # -----------------------------
    drugs_seen = state["entities_seen"]["drugs"]
    for d in drugs:
        if d not in drugs_seen:
            drugs_seen.add(d)

    update_conversation(cid, drugs_seen=list(drugs_seen))
    active_drugs = list(drugs_seen)

    # -----------------------------
    # INTENT STICKY
    # -----------------------------
    last_intent = state.get("last_intent")
    resolved_intent = intent if intent != "GENERAL" else last_intent or "GENERAL"
    update_conversation(cid, last_intent=resolved_intent)

    # -----------------------------
    # MODE
    # -----------------------------
    mode = "COMPARISON" if len(active_drugs) > 1 else "SINGLE"
    update_conversation(cid, mode=mode)

    # -----------------------------
    # ORCHESTRATION (CACHED) — PASSING ALL CONDITIONS
    # -----------------------------
    evidence_cache = state.get("evidence_cache", {})
    condition_key = "|".join(sorted(active_conditions))

    async with httpx.AsyncClient(timeout=120) as client:
        for drug in active_drugs:
            cache_key = f"{drug}|{condition_key}|{resolved_intent}"

            if cache_key not in evidence_cache:
                auth_header = request.headers.get("Authorization")
                headers = {}
                if auth_header:
                    headers["Authorization"] = auth_header

                resp = await client.post(
                    f"{BASE_URL}/api/orchestrate",
                    json={
                        "drug": drug,
                        "conditions": active_conditions,
                        "intent": resolved_intent,
                    },
                    headers=headers,
                )

                resp.raise_for_status()
                evidence_cache[cache_key] = resp.text


    update_conversation(cid, evidence_cache=evidence_cache)

    # -----------------------------
    # SYNTHESIS WITH GROQ (LLAMA 3.3 70B)
    # -----------------------------
    if mode == "SINGLE":
        drug_label = active_drugs[0] if active_drugs else "NONE"
        cache_key = f"{drug_label}|{condition_key}|{resolved_intent}"
        full_evidence = evidence_cache.get(cache_key, "")

        prompt = SYSTEM_IDENTITY.format(
            drug=drug_label,
            condition=", ".join(active_conditions),
            intent=resolved_intent,
            evidence=full_evidence,
        )

        full_prompt = f"USER QUESTION: {message}\n\n{prompt}"

        answer = await run_groq(full_prompt)

    else:  # COMPARISON mode
        blocks = []
        for drug in active_drugs:
            cache_key = f"{drug}|{condition_key}|{resolved_intent}"
            ev = evidence_cache.get(cache_key, "")
            if ev:
                blocks.append(f"[{drug.upper()}]\n" + ev)

        prompt = COMPARISON_PROMPT.format(
            condition=", ".join(active_conditions),
            drug_list="\n".join(f"- {d}" for d in active_drugs),
            evidence="\n\n".join(blocks),
        )

        full_prompt = f"USER QUESTION: {message}\n\n{prompt}"
        answer = await run_groq(full_prompt)

    # -----------------------------
    # VISUALIZATION CALL — ONLY IN SINGLE MODE
    # -----------------------------
    visualizations: Optional[Dict[str, Any]] = None

    # Only trigger visualization for SINGLE mode (clean, no confusion)
    if mode == "SINGLE" and resolved_intent in ["COMMERCIAL", "FULL_OPPORTUNITY"]:
        market_text = ""
        clinical_text = ""

        # Extract from single drug evidence
        if "[AGENT: MARKET]" in full_evidence:
            parts = full_evidence.split("[AGENT: MARKET]")
            if len(parts) > 1:
                market_text = parts[1].split("[AGENT:")[0].strip()

        if "[AGENT: CLINICAL]" in full_evidence:
            parts = full_evidence.split("[AGENT: CLINICAL]")
            if len(parts) > 1:
                clinical_text = parts[1].split("[AGENT:")[0].strip()

        if market_text or clinical_text:
            try:
                async with httpx.AsyncClient() as viz_client:
                    viz_resp = await viz_client.post(
                        f"{BASE_URL}/api/visualize",
                        json={
                            "market_data": market_text,
                            "clinical_data": clinical_text,
                        },
                        timeout=30.0
                    )
                    if viz_resp.status_code == 200:
                        visualizations = viz_resp.json()
                    else:
                        logger.warning(f"Visualization failed: {viz_resp.status_code}")
            except Exception as e:
                logger.error(f"Visualization error: {e}")

    # -----------------------------
    # SAVE CHAT HISTORY TO DATABASE WITH USER_ID
    # -----------------------------
    db = SessionLocal()
    try:
            db.add(ChatHistory(
                conversation_id=cid,
                user_id=current_user.user_id,
                question=message,
                answer=answer,
                conditions=active_conditions,
                active_drugs=active_drugs,
                intent=resolved_intent,
                mode=mode,
                visualizations_json=json.dumps(visualizations) if visualizations else None,
            ))
        
            db.commit()
    except Exception as e:
            logger.error(f"Failed to save chat history: {e}")
            db.rollback()
    finally:
            db.close()


    # -----------------------------
    # DRAMATIC PAUSE FOR HACKATHON DEMO
    # -----------------------------
    await asyncio.sleep(10)

    logger.info("NovusAI deep analysis complete — delivering evidence-based insights.")

    # -----------------------------
    # RETURN
    # -----------------------------
    return {
        "type": "analysis",
        "answer": answer,
        "conversation_id": cid,
        "mode": mode,
        "active_drugs": active_drugs,
        "condition": active_conditions,
        "intent": resolved_intent,
        "visualizations": visualizations,
    }