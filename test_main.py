import pytest
from fastapi.testclient import TestClient
from main import app, price_cache
import time

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_cache():
    """Fixture to clear the cache before each test."""
    price_cache.clear()

def test_get_price_success(mocker):
    """
    Test successful retrieval of a cryptocurrency price.
    """
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "bitcoin": {
            "usd": 65000,
            "usd_24h_change": 5.5
        }
    }
    mocker.patch("requests.get", return_value=mock_response)

    response = client.get("/price/bitcoin")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["source"] == "live"
    assert data["data"]["symbol"] == "bitcoin"
    assert data["data"]["price"] == 65000

def test_get_price_not_found(mocker):
    """
    Test retrieval of a non-existent cryptocurrency.
    """
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}  # Empty response for not found
    mocker.patch("requests.get", return_value=mock_response)

    response = client.get("/price/nonexistentcoin")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]

def test_caching(mocker):
    """
    Test if the caching mechanism is working.
    """
    # First request to cache the data
    mock_response_live = mocker.Mock()
    mock_response_live.status_code = 200
    mock_response_live.json.return_value = {
        "ethereum": {
            "usd": 3500,
            "usd_24h_change": 2.1
        }
    }
    mocker.patch("requests.get", return_value=mock_response_live)

    response1 = client.get("/price/ethereum")
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["status"] == "success"
    assert data1["source"] == "live"

    # Second request should come from cache (no API call)
    response2 = client.get("/price/ethereum")
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["status"] == "success"
    assert data2["source"] == "cache"

    # Wait for cache to expire
    time.sleep(61)

    # Third request should be live again
    mocker.patch("requests.get", return_value=mock_response_live) # Re-patch for the new call
    response3 = client.get("/price/ethereum")
    assert response3.status_code == 200
    data3 = response3.json()
    assert data3["status"] == "success"
    assert data3["source"] == "live"

def test_rate_limit_with_cache(mocker):
    """
    Test rate limit handling when there is cached data.
    """
    # First, cache the data
    mock_response_live = mocker.Mock()
    mock_response_live.status_code = 200
    mock_response_live.json.return_value = {"solana": {"usd": 150}}
    mocker.patch("requests.get", return_value=mock_response_live)
    client.get("/price/solana")

    # Wait for cache to expire
    time.sleep(61)

    # Now, simulate a rate limit error
    mock_response_ratelimit = mocker.Mock()
    mock_response_ratelimit.status_code = 429
    mocker.patch("requests.get", return_value=mock_response_ratelimit)

    response = client.get("/price/solana")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "warning"
    assert data["source"] == "expired_cache"
    assert data["data"]["price"] == 150

def test_rate_limit_no_cache(mocker):
    """
    Test rate limit handling when there is no cached data.
    """
    mock_response_ratelimit = mocker.Mock()
    mock_response_ratelimit.status_code = 429
    mocker.patch("requests.get", return_value=mock_response_ratelimit)

    response = client.get("/price/cardano")
    assert response.status_code == 429
    assert "Rate Limit Exceeded" in response.json()["detail"]