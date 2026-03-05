"""
CoinGecko data source for cryptocurrency prices and technical indicators.

Uses OpenBB as primary source, falls back to CoinGecko direct API.
Free API, 30 calls/min, no API key required for fallback.
"""

import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# Import OpenBB service for unified data access
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import openbb_service


# Ticker -> CoinGecko ID mapping (for fallback)
CRYPTO_IDS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'SOL': 'solana',
    'ADA': 'cardano',
    'DOGE': 'dogecoin',
}


def fetch_crypto_data() -> Dict[str, Dict[str, Any]]:
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching crypto data...")

    results = {}
    for ticker, coin_id in CRYPTO_IDS.items():
        data = _fetch_coin_data(ticker, coin_id)
        if data:
            results[ticker] = data
        time.sleep(1)  # Small delay between requests

    print(f"  OK {len(results)} coins fetched")
    return results


def _fetch_coin_data(ticker: str, coin_id: str) -> Optional[Dict[str, Any]]:
    """Fetch price history and calculate SMAs for a single coin."""
    
    # Try OpenBB first for historical prices
    prices = openbb_service.get_historical_prices(ticker, days=210, asset_type="crypto")
    
    # Fallback to CoinGecko direct API if OpenBB fails
    if not prices:
        prices = _fetch_prices_coingecko(ticker, coin_id)
    
    if len(prices) < 30:
        print(f"  ! Not enough price data for {ticker} ({len(prices)} days)")
        return None

    current_price = prices[-1]

    # Short-term SMAs (for more frequent signals)
    sma_10 = sum(prices[-10:]) / 10 if len(prices) >= 10 else None
    sma_20 = sum(prices[-20:]) / 20 if len(prices) >= 20 else None
    sma_30 = sum(prices[-30:]) / 30 if len(prices) >= 30 else None

    # Medium/long-term SMAs
    sma_50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else None
    sma_200 = sum(prices[-200:]) / 200 if len(prices) >= 200 else None

    # Golden cross: SMA50 > SMA200 (long-term bullish)
    golden_cross = sma_50 > sma_200 if (sma_50 and sma_200) else False

    # Short-term bullish: SMA10 > SMA30 (faster momentum signal)
    short_term_bullish = sma_10 > sma_30 if (sma_10 and sma_30) else False

    # Check if golden cross happened recently (SMA50 was below SMA200 yesterday)
    prev_sma_50 = sum(prices[-51:-1]) / 50 if len(prices) >= 51 else None
    prev_sma_200 = sum(prices[-201:-1]) / 200 if len(prices) >= 201 else None
    fresh_golden_cross = False
    if prev_sma_50 and prev_sma_200 and sma_50 and sma_200:
        fresh_golden_cross = prev_sma_50 <= prev_sma_200 and sma_50 > sma_200

    # Check if short-term cross happened recently
    prev_sma_10 = sum(prices[-11:-1]) / 10 if len(prices) >= 11 else None
    prev_sma_30 = sum(prices[-31:-1]) / 30 if len(prices) >= 31 else None
    fresh_short_term_cross = False
    if prev_sma_10 and prev_sma_30 and sma_10 and sma_30:
        fresh_short_term_cross = prev_sma_10 <= prev_sma_30 and sma_10 > sma_30

    # Calculate RSI
    try:
        from engine.indicators import rsi as calc_rsi
        rsi_14 = calc_rsi(prices, 14)
    except ImportError:
        rsi_14 = None

    return {
        'price': current_price,
        # Short-term SMAs
        'sma_10': sma_10,
        'sma_20': sma_20,
        'sma_30': sma_30,
        # Long-term SMAs
        'sma_50': sma_50,
        'sma_200': sma_200,
        # Signals
        'golden_cross': golden_cross,
        'fresh_golden_cross': fresh_golden_cross,
        'short_term_bullish': short_term_bullish,
        'fresh_short_term_cross': fresh_short_term_cross,
        'rsi_14': rsi_14,
        'prices_history': prices[-30:],  # Last 30 days for context
    }


def _fetch_prices_coingecko(ticker: str, coin_id: str) -> list:
    """Fallback: Fetch price history directly from CoinGecko API."""
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
            params={'vs_currency': 'usd', 'days': 210},
            timeout=15
        )
        if resp.status_code != 200:
            print(f"  ! CoinGecko returned {resp.status_code} for {ticker}")
            return []

        data = resp.json()
        prices = [p[1] for p in data.get('prices', [])]
        return prices

    except Exception as e:
        print(f"  ERROR fetching {ticker} from CoinGecko: {e}")
        return []
