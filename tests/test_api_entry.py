import pytest
from litestar.testing import TestClient

from ttd.api.app import create_app


@pytest.mark.usefixtures("reset_db_state")
def test_api_health_route() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "db_path" in payload
