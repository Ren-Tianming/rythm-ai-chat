from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_has_security_and_request_id_headers() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "request-test"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_validation_error_uses_stable_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/auth/verify-email", json={"token": "short"})
    assert response.status_code == 422
    payload = response.json()["error"]
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["request_id"]


def test_unexpected_error_uses_stable_contract() -> None:
    app = create_app()

    @app.get("/test/boom")
    async def boom() -> None:
        raise RuntimeError("sensitive detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test/boom")
    assert response.status_code == 500
    payload = response.json()["error"]
    assert payload["code"] == "INTERNAL_ERROR"
    assert payload["message"] == "An unexpected error occurred"
    assert "sensitive detail" not in response.text
