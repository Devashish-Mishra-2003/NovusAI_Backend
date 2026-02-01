from typing import List, Optional
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.services.patent_service import search_patents_raw_xml

router = APIRouter()


class PatentsRequest(BaseModel):
    drug: Optional[str] = Field(None, description="INN drug name")
    conditions: List[str] = Field(default_factory=list, max_items=3)


@router.post("/patents")
def patents_agent(req: PatentsRequest):
    text = search_patents_raw_xml(req.drug, req.conditions)
    return Response(content=text, media_type="text/plain")
