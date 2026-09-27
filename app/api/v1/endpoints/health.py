from fastapi import APIRouter, status

from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """Return application liveness status."""
    return HealthResponse(status="ok")
