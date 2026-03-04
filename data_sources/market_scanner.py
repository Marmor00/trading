"""
Market Scanner: fetches price history for a universe of tickers
and calculates all technical indicators.

Uses yfinance for data (already in requirements.txt).
Results are cached per run so multiple profiles share one scan.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

import yfinance as yf

from engine.indicators import rsi, macd, bollinger_bands, sma_crossover, week52_position


# Ticker universes
UNIVERSES = {
    'mega_cap': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'tech_growth': ['AMD', 'CRM', 'NFLX', 'SQ', 'PLTR', 'UBER'],
    'etf_universe': ['QQQ', 'IWM', 'DIA', 'GLD', 'XBI', 'TLT'],
}

# Module-level cache (survives within a single process run)
_scan_cache: Dict[str, Dict] = {}


def scan_market(universes: List[str] = None) -> Dict[str, Dict]:
    """Scan all tickers in the specified universes.

    Returns dict keyed by ticker:
    {
        'AAPL': {
            'price': 185.50,
            'prices': [180.1, 181.2, ...],   # ~250 days
            'rsi_14': 42.5,
            'macd': { 'macd_line': ..., 'crossover_up': True/False, ... },
            'bollinger': { 'upper': ..., 'lower': ..., 'pct_b': 0.35, ... },
            'sma_cross_50_200': { 'golden_cross': False, 'bullish': True, ... },
            'week52': { 'pct_from_high': -8.5, 'position': 72.0, ... },
            'universe': 'mega_cap',
        },
        ...
    }
    """
    global _scan_cache
    if _scan_cache:
        return _scan_cache

    if universes is None:
        universes = ['mega_cap', 'tech_growth', 'etf_universe']

    # Build ticker -> universe mapping
    ticker_universe = {}
    for univ_name in universes:
        tickers = UNIVERSES.get(univ_name, [])
        for t in tickers:
            ticker_universe[t] = univ_name

    all_tickers = list(ticker_universe.keys())
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Market Scanner: scanning {len(all_tickers)} tickers...")

    results = {}

    # Fetch in batches to be respectful of yfinance rate limits
    batch_size = 5
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
        for ticker in batch:
            data = _scan_single_ticker(ticker, ticker_universe[ticker])
            if data:
                results[ticker] = data
        if i + batch_size < len(all_tickers):
            time.sleep(1)  # Rate limit pause between batches

    print(f"  OK {len(results)}/{len(all_tickers)} tickers scanned successfully")
    _scan_cache = results
    return results


def _scan_single_ticker(ticker: str, universe: str) -> Optional[Dict]:
    """Fetch history and calculate all indicators for one ticker."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')  # ~252 trading days

        if hist.empty or len(hist) < 50:
            print(f"  ! {ticker}: insufficient data ({len(hist)} days)")
            return None

        closes = hist['Close'].tolist()
        current_price = closes[-1]

        return {
            'price': current_price,
            'prices': closes,
            'volume_avg': hist['Volume'].tail(20).mean() if 'Volume' in hist.columns else 0,
            'universe': universe,
            'rsi_14': rsi(closes, 14),
            'macd': macd(closes),
            'bollinger': bollinger_bands(closes),
            'sma_cross_50_200': sma_crossover(closes, 50, 200),
            'week52': week52_position(closes),
        }

    except Exception as e:
        print(f"  ! {ticker} scan error: {e}")
        return None


def clear_scan_cache():
    """Clear the scan cache (call at start of each run)."""
    global _scan_cache
    _scan_cache = {}
