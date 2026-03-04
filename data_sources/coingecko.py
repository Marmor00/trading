"""
CoinGecko data source for cryptocurrency prices and technical indicators.

Free API, 30 calls/min, no API key required.
Source: https://www.coingecko.com/en/api
"""

import requests
from datetime import datetime


# Ticker -> CoinGecko ID mapping
CRYPTO_IDS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
}


def fetch_crypto_data():
    """Fetch crypto price data with SMA calculations for supported coins.

    Returns dict with ticker as key:
    {
        'BTC': {
            'price': 95000.0,
            'sma_50': 92000.0,
            'sma_200': 88000.0,
            'golden_cross': True,   # SMA50 > SMA200
            'prices_history': [...]
        },
        'ETH': { ... }
    }
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching crypto data from CoinGecko...")

    results = {}
    for ticker, coin_id in CRYPTO_IDS.items():
        data = _fetch_coin_data(ticker, coin_id)
        if data:
            results[ticker] = data

    print(f"  OK {len(results)} coins fetched")
    return results


def _fetch_coin_data(ticker, coin_id):
    """Fetch price history and calculate SMAs for a single coin."""
    try:
        # Get 210 days of history (enough for 200-day SMA)
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={'vs_currency': 'usd', 'days': 210},
            timeout=15
        )
        if resp.status_code != 200:
            print(f"  ! CoinGecko returned {resp.status_code} for {ticker}")
            return None

        data = resp.json()
        prices = [p[1] for p in data.get('prices', [])]

        if len(prices) < 50:
            print(f"  ! Not enough price data for {ticker} ({len(prices)} days)")
            return None

        current_price = prices[-1]
        sma_50 = sum(prices[-50:]) / 50
        sma_200 = sum(prices[-200:]) / min(len(prices), 200) if len(prices) >= 50 else None

        golden_cross = sma_50 > sma_200 if sma_200 else None

        # Check if cross happened recently (SMA50 was below SMA200 yesterday)
        prev_sma_50 = sum(prices[-51:-1]) / 50 if len(prices) >= 51 else None
        fresh_cross = False
        if prev_sma_50 and sma_200:
            fresh_cross = prev_sma_50 < sma_200 and sma_50 > sma_200

        return {
            'price': current_price,
            'sma_50': sma_50,
            'sma_200': sma_200,
            'golden_cross': golden_cross,
            'fresh_golden_cross': fresh_cross,
            'prices_history': prices[-30:],  # Last 30 days for context
        }

    except Exception as e:
        print(f"  ERROR fetching {ticker}: {e}")
        return None
