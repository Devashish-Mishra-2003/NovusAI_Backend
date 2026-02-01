from typing import Dict, Any, Optional, List
import time
import uuid

_CONVERSATIONS: Dict[str, Dict[str, Any]] = {}


def create_conversation() -> str:
    conversation_id = str(uuid.uuid4())

    _CONVERSATIONS[conversation_id] = {
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

    return conversation_id


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    return _CONVERSATIONS.get(conversation_id)


def update_conversation(
    conversation_id: str,
    *,
    orchestration: Optional[Dict[str, Any]] = None,
    visualization: Optional[Dict[str, Any]] = None,
    full_summary_text: Optional[str] = None,
    fetched_domains: Optional[Dict[str, bool]] = None,

    active_conditions: Optional[List[str]] = None,
    active_drug: Optional[str] = None,

    drugs_seen: Optional[List[str]] = None,
    mode: Optional[str] = None,
    last_intent: Optional[str] = None,

    evidence_cache: Optional[Dict[str, str]] = None,

    last_discussed_drug: Optional[str] = None,
    last_discussed_condition: Optional[str] = None,

    depth: Optional[str] = None,
    chat_entry: Optional[Dict[str, str]] = None,
):
    state = _CONVERSATIONS.get(conversation_id)
    if not state:
        return

    if orchestration is not None:
        state["orchestration"] = orchestration

    if visualization is not None:
        state["visualization"] = visualization

    if full_summary_text is not None:
        state["full_summary_text"] = full_summary_text

    if fetched_domains is not None:
        state["fetched_domains"].update(fetched_domains)

    if active_conditions is not None:
        state["active_context"]["conditions"] = active_conditions

    if active_drug is not None:
        state["active_context"]["drug"] = active_drug

    if drugs_seen is not None:
        state["entities_seen"]["drugs"] = set(drugs_seen)

    if mode is not None:
        state["mode"] = mode

    if last_intent is not None:
        state["last_intent"] = last_intent

    if evidence_cache is not None:
        state["evidence_cache"] = evidence_cache

    if last_discussed_drug is not None:
        state["last_discussed"]["drug"] = last_discussed_drug

    if last_discussed_condition is not None:
        state["last_discussed"]["condition"] = last_discussed_condition

    if depth is not None:
        state["depth"] = depth

    if chat_entry:
        state["chat_history"].append(chat_entry)
        state["chat_history"] = state["chat_history"][-10:]

    state["updated_at"] = time.time()
