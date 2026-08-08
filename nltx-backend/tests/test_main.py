import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.database import Base
from app.database import get_db

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_register_user(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "first_name": "Test",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201
    assert response.json()["username"] == "testuser"


def test_login_user(client):
    response = client.post(
        "/api/auth/login",
        data={"username": "testuser", "password": "Password123!"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
