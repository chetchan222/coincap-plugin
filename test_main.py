import pytest
from fastapi.testclient import TestClient
from main import app, price_cache
import time
import os

# Set a dummy API key for testing purposes
os.environ["COINGECKO_API_KEY"] = "dummy_key"

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
    # Check that the response is a plain text string
    assert response.headers['content-type'] == 'text/plain; charset=utf-8'
    assert "The price of bitcoin is 65000 USD" in response.text

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
    assert "The price of ethereum is 3500 USD" in response1.text

    # Manually check cache content
    assert "ethereum" in price_cache
    assert price_cache["ethereum"]["data"] == response1.text

    # Second request should come from cache
    # We can even remove the patch to ensure no API call is made
    mocker.stopall()
    response2 = client.get("/price/ethereum")
    assert response2.status_code == 200
    assert response2.text == response1.text # Should be identical to cached string

def test_rate_limit_with_cache(mocker):
    """
    Test rate limit handling when there is cached data.
    """
    # First, cache the data
    mock_response_live = mocker.Mock()
    mock_response_live.status_code = 200
    mock_response_live.json.return_value = {"solana": {"usd": 150, "usd_24h_change": 1.0}}
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
    assert "(Stale Data due to Rate Limit)" in response.text
    assert "The price of solana is 150 USD" in response.text

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
