"""
Price fetching service with multiple providers.

Providers:
- Massive API (stocks, requires API key)
- Yahoo Finance via yfinance (stocks, ETFs, free)
- CoinGecko (crypto, free, 30 calls/min)
"""

import os
import time
import requests

from engine.models import AssetType


MASSIVE_API_KEY = os.environ.get('MASSIVE_API_KEY', '')
MASSIVE_BASE_URL = "https://api.massive.com/v1"

# Simple in-memory cache to avoid duplicate API calls in the same run
_price_cache = {}


def get_price(ticker, asset_type=AssetType.STOCK):
    """Get current price for a ticker. Returns float or None."""
    cache_key = f"{ticker}:{asset_type.value}"
    if cache_key in _price_cache:
        return _price_cache[cache_key]

    price = None
    if asset_type == AssetType.CRYPTO:
        price = _get_price_coingecko(ticker)
    else:
        price = _get_price_massive(ticker) or _get_price_yfinance(ticker)

    if price:
        _price_cache[cache_key] = price
    return price


def clear_price_cache():
    """Clear the price cache (call at the start of each run)."""
    _price_cache.clear()


def _get_price_massive(ticker):
    """Fetch price from Massive API."""
    if not MASSIVE_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{MASSIVE_BASE_URL}/stocks/{ticker}/quotes/latest",
            headers={"Authorization": f"Bearer {MASSIVE_API_KEY}"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            price = data.get('close') or data.get('price') or data.get('last')
            if price:
                return float(price)
    except Exception:
        pass
    return None


def _get_price_yfinance(ticker):
    """Fetch price from Yahoo Finance API."""
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d",
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if resp.status_code == 200:
            price = resp.json()['chart']['result'][0]['meta'].get('regularMarketPrice')
            if price:
                return float(price)
    except Exception:
        pass
    return None


# CoinGecko ticker mapping (our ticker -> coingecko id)
CRYPTO_IDS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'ADA': 'cardano',
    'DOT': 'polkadot',
    'AVAX': 'avalanche-2',
    'LINK': 'chainlink',
    'MATIC': 'matic-network',
    'XRP': 'ripple',
    'DOGE': 'dogecoin',
}


def _get_price_coingecko(ticker):
    """Fetch price from CoinGecko free API."""
    coin_id = CRYPTO_IDS.get(ticker.upper())
    if not coin_id:
        return None
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            price = data.get(coin_id, {}).get('usd')
            if price:
                return float(price)
    except Exception:
        pass
    return None


def get_crypto_history(ticker, days=200):
    """Fetch historical prices from CoinGecko for SMA calculations."""
    coin_id = CRYPTO_IDS.get(ticker.upper())
    if not coin_id:
        return []
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}",
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            prices = [p[1] for p in data.get('prices', [])]
            return prices
    except Exception:
        pass
    return []
