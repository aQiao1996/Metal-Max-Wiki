from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ai import router as ai_router
from app.api.auth import router as auth_router
from app.api.equipment import router as equipment_router
from app.api.game_versions import router as game_versions_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers
from app.db.session import engine


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(game_versions_router, prefix=settings.api_v1_prefix)
    application.include_router(equipment_router, prefix=settings.api_v1_prefix)
    application.include_router(knowledge_router, prefix=settings.api_v1_prefix)
    application.include_router(auth_router, prefix=settings.api_v1_prefix)
    application.include_router(ai_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
