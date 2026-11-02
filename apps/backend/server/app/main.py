from fastapi import FastAPI

from app.api.game_versions import router as game_versions_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.exception_handlers import register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name)
    register_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(game_versions_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
