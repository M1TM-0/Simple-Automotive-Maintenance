import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_api_root_returns_standardized_json_404():
    client = APIClient()

    response = client.get("/api/")

    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
