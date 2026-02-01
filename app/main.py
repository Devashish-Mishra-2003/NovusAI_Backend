# app/main.py

import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from jose import JWTError, jwt
from datetime import datetime

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("novus-main")

from app.db import Base, engine
from app.models.auth import Company, User
from app.models.chat import ChatHistory

Base.metadata.create_all(
    bind=engine,
    tables=[
        Company.__table__,
        User.__table__,
        ChatHistory.__table__,
    ],
)

logger.info("✅ Database tables created successfully")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        public_paths = {
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        if request.url.path in public_paths or request.url.path.startswith("/auth/"):
            return await call_next(request)

        # 🔐 ONLY protect synthesis
        if request.url.path == "/api/synthesize":
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(status_code=401, detail="Missing or invalid token")

            token = auth_header.split(" ")[1]

            try:
                payload = jwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM]
                )
                user_id_str = payload.get("sub")
                if not user_id_str:
                    raise HTTPException(status_code=401, detail="Invalid token: missing sub")
                request.state.user_id = int(user_id_str)
            except JWTError:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

        return await call_next(request)


from app.agents.auth import router as auth_router
from app.agents.patents import router as patents_router
from app.agents.clinical import router as clinical_router
from app.agents.literature import router as literature_router
from app.agents.web_intelligence import router as web_router
from app.agents.market_agent import router as market_router
from app.agents.internal_knowledge import router as internal_knowledge_router
from app.agents.orchestration import router as orchestration_router
from app.agents.synthesis import router as synthesis_router
from app.agents.visualization import router as visualization_router
from app.agents.pdf import router as pdf_router
from app.pre_synthesis.api import router as mistral_router
from app.pre_synthesis.synonym_api import router as synonym_router
from app.agents.history import router as history_router
from app.api.documents import router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting NovusAI Drug Repurposing Platform")
    yield
    logger.info("🛑 Shutting down NovusAI")


app = FastAPI(
    title="NovusAI Drug Repurposing Platform",
    description="Secure, Multi-User AI Drug Repurposing Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "HTTPBearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    # ❌ DO NOT apply global security (routes differ)
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

app.add_middleware(AuthMiddleware)

# ✅ FIXED CORS (DEPLOYMENT SAFE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # "https://yourdomain.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "NovusAI is running with auth enabled",
    }


app.include_router(auth_router)

app.include_router(patents_router, prefix="/api", tags=["patents"])
app.include_router(clinical_router, prefix="/api", tags=["clinical"])
app.include_router(literature_router, prefix="/api", tags=["literature"])
app.include_router(web_router, prefix="/api", tags=["web"])
app.include_router(market_router, prefix="/api", tags=["market"])
app.include_router(internal_knowledge_router, prefix="/api", tags=["internal_knowledge"])
app.include_router(orchestration_router, prefix="/api", tags=["orchestration"])
app.include_router(synthesis_router, prefix="/api", tags=["synthesis"])
app.include_router(visualization_router, prefix="/api", tags=["visualization"])
app.include_router(pdf_router, prefix="/api", tags=["pdf"])
app.include_router(mistral_router, prefix="/api", tags=["pre-synthesis"])
app.include_router(synonym_router, prefix="/api", tags=["synonyms"])
app.include_router(history_router, prefix="/api", tags=["history"])
app.include_router(documents_router, prefix="/api", tags=["documents"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )