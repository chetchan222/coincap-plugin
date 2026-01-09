from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import time

app = FastAPI(
    title="Crypto Price Plugin",
    description="Get real-time crypto prices with caching to prevent rate limits.",
    version="1.0.0",
    servers=[
        {"url": "https://YOUR-APP-NAME.onrender.com", "description": "Render Production Server"} 
    ]
)

# 允許跨域請求 (對 HiAgent 很重要)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 簡單的內存緩存 { "bitcoin": { "price": 90000, "timestamp": 12345678 } }
price_cache = {}
CACHE_DURATION = 60  # 緩存 60 秒

@app.get("/health", summary="Health Check", operation_id="healthCheck")
def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "ok"}

@app.get("/price/{symbol}", summary="Get Crypto Price", operation_id="getPrice")
def get_crypto_price(symbol: str):
    """
    獲取加密貨幣價格 (例如: bitcoin, ethereum).
    包含 60 秒緩存以避免 CoinGecko 429 錯誤。
    """
    symbol = symbol.lower()
    current_time = time.time()

    # 1. 檢查緩存
    if symbol in price_cache:
        last_data = price_cache[symbol]
        if current_time - last_data["timestamp"] < CACHE_DURATION:
            return {
                "status": "success",
                "source": "cache",
                "data": last_data["data"]
            }

    # 2. 請求 CoinGecko API
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol}&vs_currencies=usd&include_24hr_change=true"
    
    try:
        response = requests.get(url, timeout=10)

        # 1. Handle Rate Limit
        if response.status_code == 429:
            if symbol in price_cache:
                return {"status": "warning", "source": "expired_cache", "data": price_cache[symbol]["data"], "detail": "Rate limit hit, returning old data"}
            else:
                raise HTTPException(status_code=429, detail="CoinGecko Rate Limit Exceeded. Try again later.")

        # 2. Handle other non-200 responses
        if response.status_code != 200:
             raise HTTPException(status_code=response.status_code, detail=f"Upstream API Error: {response.text}")

        # 3. Handle successful response
        data = response.json()
        
        # Safely check for data existence
        if not data or symbol not in data:
            raise HTTPException(status_code=404, detail=f"Currency '{symbol}' not found or price data unavailable.")
        
        coin_data = data[symbol]
        if not coin_data or "usd" not in coin_data:
            raise HTTPException(status_code=404, detail=f"Currency '{symbol}' not found or price data unavailable.")

        result = {
            "symbol": symbol,
            "currency": "usd",
            "price": coin_data["usd"],
            "change_24h": coin_data.get("usd_24h_change", 0)
        }

        # 4. Update cache
        price_cache[symbol] = {
            "timestamp": current_time,
            "data": result
        }

        return {"status": "success", "source": "live", "data": result}

    except HTTPException as e:
        raise e  # Re-raise HTTPException so FastAPI can handle it
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="CoinGecko API request timed out.")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error connecting to CoinGecko API: {e}")
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
