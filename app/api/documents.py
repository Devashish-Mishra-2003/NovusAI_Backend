from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from uuid import uuid4
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.schemas import AuthUser
from app.db import get_db
from app.services.supabase_client import supabase

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    # backend safety
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(status_code=400, detail="Only PDF and TXT allowed")

    company_id = current_user.company_id
    ext = file.filename.split(".")[-1]
    storage_path = f"{company_id}/{uuid4()}.{ext}"

    content = await file.read()

    try:
        result = supabase.storage.from_("company_docs").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": file.content_type},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    return {
        "message": "Uploaded successfully",
        "path": result.path,
        "filename": file.filename,
    }
