import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault(
    "DATABASE_URL",
    os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://fleet:fleet@localhost:5433/fleet_test",
    ),
)
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.db.base import Base
from app.db.seed import seed_reference_data
from app.db.session import get_db
from app.domain.event_log_handler import make_domain_event_log_handler
from app.domain.events import publisher
from app.main import create_app
from app.services.rate_limiter import vehicle_rate_limiter

test_engine = create_engine(os.environ["DATABASE_URL"], future=True, pool_pre_ping=True)
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    with TestSessionLocal() as db:
        seed_reference_data(db)
    vehicle_rate_limiter.reset()
    publisher.clear()
    yield
    publisher.clear()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    with TestSessionLocal() as db:
        yield db


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        with TestSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        publisher.clear()
        publisher.subscribe(make_domain_event_log_handler(TestSessionLocal))
        yield test_client
    app.dependency_overrides.clear()
