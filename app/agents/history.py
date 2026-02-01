# app/agents/history.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime

from app.db import get_db
from app.models.chat import ChatHistory
from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthUser

router = APIRouter(prefix="/api/history", tags=["history"])


# ======================================================
# 1️⃣ LIST CONVERSATIONS (PER USER)
# ======================================================
@router.get("/conversations")
def list_conversations(
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ChatHistory)
        .filter(ChatHistory.user_id == current_user.user_id)
        .order_by(ChatHistory.id.desc())
        .all()
    )

    conversations: Dict[str, Dict] = {}

    for row in rows:
        if row.conversation_id not in conversations:
            conversations[row.conversation_id] = {
                "conversation_id": row.conversation_id,
                "last_question": row.question,
                "last_updated": row.id,
            }

    return list(conversations.values())


# ======================================================
# 2️⃣ GET FULL CONVERSATION
# ======================================================
@router.get("/conversations/{conversation_id}")
def get_conversation_history(
    conversation_id: str,
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.conversation_id == conversation_id,
            ChatHistory.user_id == current_user.user_id,
        )
        .order_by(ChatHistory.id.asc())
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = []
    for row in rows:
        messages.append({
            "role": "user",
            "content": row.question,
        })
        messages.append({
            "role": "assistant",
            "content": row.answer,
            "visualizations": (
                None if not row.visualizations_json
                else row.visualizations_json
            ),
        })

    return {
        "conversation_id": conversation_id,
        "messages": messages,
    }
