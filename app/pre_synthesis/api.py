from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.pre_synthesis.groq_interpreter import interpret_query

router = APIRouter()


class ParseRequest(BaseModel):
    query: str


class ParseResponse(BaseModel):
    drug: List[str]
    conditions: List[str]
    intent: str


@router.post("/nlp/interpret", response_model=ParseResponse)
def interpret(req: ParseRequest):
    parsed = interpret_query(req.query)

    return {
        "drug": parsed.get("drug", []),
        "conditions": parsed.get("conditions", []),
        "intent": parsed["intent"],
    }