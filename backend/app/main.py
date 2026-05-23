from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db.session import SessionLocal
from app.domain.event_log_handler import make_domain_event_log_handler
from app.domain.events import publisher


def create_app() -> FastAPI:
    app = FastAPI(title="Fleet Telemetry Monitoring Service")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.on_event("startup")
    def configure_domain_events() -> None:
        publisher.clear()
        publisher.subscribe(make_domain_event_log_handler(SessionLocal))

    return app


app = create_app()
