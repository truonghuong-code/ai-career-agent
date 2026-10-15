from fastapi import APIRouter

from app.api.v1.endpoints.analyses import router as analyses_router
from app.api.v1.endpoints.documents import router as documents_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.qa import router as qa_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(documents_router, tags=["documents"])
api_router.include_router(qa_router, tags=["qa"])
api_router.include_router(analyses_router, tags=["analyses"])
