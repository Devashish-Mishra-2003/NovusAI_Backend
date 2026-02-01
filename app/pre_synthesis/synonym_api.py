from fastapi import APIRouter
from pydantic import BaseModel

from app.pre_synthesis.condition_synonyms import expand_condition

router = APIRouter()


class SynonymRequest(BaseModel):
    condition: str


class SynonymResponse(BaseModel):
    conditions: list[str]


@router.post("/nlp/condition-synonyms", response_model=SynonymResponse)
def condition_synonyms(req: SynonymRequest):
    return {
        "conditions": expand_condition(req.condition)
    }
