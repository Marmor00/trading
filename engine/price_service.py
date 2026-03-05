"""
Price fetching service with multiple providers.

Provider priority:
1. OpenBB SDK (unified interface, yfinance backend)
2. Massive API (stocks, requires API key)
3. Yahoo Finance direct (stocks, ETFs, free)
4. CoinGecko direct (crypto, free, 30 calls/min)
"""

import os
import requests

from engine.models import AssetType
from engine import openbb_service


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
        # Try OpenBB first, then CoinGecko fallback
        price = openbb_service.get_crypto_price(ticker) or _get_price_coingecko(ticker)
    else:
        # Try OpenBB first, then Massive, then direct Yahoo
        price = openbb_service.get_stock_price(ticker) or \
                _get_price_massive(ticker) or \
                _get_price_yfinance(ticker)

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
    """Fetch price from Yahoo Finance API (direct, no library)."""
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
    """Fetch price from CoinGecko free API (fallback)."""
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
    """
    Fetch historical prices for SMA calculations.
    
    Uses OpenBB first, falls back to CoinGecko direct API.
    """
    # Try OpenBB first
    prices = openbb_service.get_historical_prices(ticker, days=days, asset_type="crypto")
    if prices:
        return prices
    
    # Fallback to CoinGecko direct
    return _get_crypto_history_coingecko(ticker, days)


def _get_crypto_history_coingecko(ticker, days=200):
    """Fetch historical prices from CoinGecko (fallback)."""
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


def get_stock_history(ticker, days=200):
    """
    Fetch historical stock prices for SMA calculations.
    
    Uses OpenBB, falls back to yfinance direct.
    """
    # Try OpenBB first
    prices = openbb_service.get_historical_prices(ticker, days=days, asset_type="stock")
    if prices:
        return prices
    
    # Fallback to yfinance direct
    return _get_stock_history_yfinance(ticker, days)


def _get_stock_history_yfinance(ticker, days=200):
    """Fetch historical stock prices from Yahoo Finance (fallback)."""
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={days}d",
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            prices = data['chart']['result'][0]['indicators']['quote'][0].get('close', [])
            # Filter out None values
            return [p for p in prices if p is not None]
    except Exception:
        pass
    return []
