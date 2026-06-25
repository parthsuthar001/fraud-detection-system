from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health", summary="Health check")
async def health_check():
    return {
        "status": "healthy",
        "service": "api-gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
