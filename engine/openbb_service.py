"""
OpenBB SDK wrapper for unified financial data access.

Provides a clean interface to OpenBB with graceful fallbacks.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try to import OpenBB - may not be available in all environments
_openbb_available = False
_obb = None

try:
    from openbb import obb
    _obb = obb
    _openbb_available = True
    logger.info("OpenBB SDK loaded successfully")
except ImportError as e:
    logger.warning(f"OpenBB SDK not available: {e}. Using fallback providers.")


def is_available() -> bool:
    """Check if OpenBB SDK is available."""
    return _openbb_available


def get_stock_price(ticker: str) -> Optional[float]:
    """
    Get current stock price via OpenBB (yfinance provider).
    
    Args:
        ticker: Stock symbol (e.g., 'AAPL', 'SPY')
    
    Returns:
        Current price as float, or None if unavailable
    """
    if not _openbb_available:
        return None
    
    try:
        # Use yfinance provider for stock quotes
        result = _obb.equity.price.quote(ticker, provider="yfinance")
        if result and hasattr(result, 'results') and result.results:
            data = result.results[0]
            # Try different price fields
            price = getattr(data, 'last_price', None) or \
                    getattr(data, 'regular_market_price', None) or \
                    getattr(data, 'price', None) or \
                    getattr(data, 'close', None)
            if price:
                return float(price)
    except Exception as e:
        logger.debug(f"OpenBB stock price failed for {ticker}: {e}")
    
    return None


def get_crypto_price(ticker: str) -> Optional[float]:
    """
    Get current crypto price via OpenBB.
    
    Args:
        ticker: Crypto symbol (e.g., 'BTC', 'ETH')
    
    Returns:
        Current price in USD as float, or None if unavailable
    """
    if not _openbb_available:
        return None
    
    # Map common tickers to full symbol format
    symbol_map = {
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD',
        'SOL': 'SOL-USD',
        'ADA': 'ADA-USD',
        'DOT': 'DOT-USD',
        'AVAX': 'AVAX-USD',
        'LINK': 'LINK-USD',
        'MATIC': 'MATIC-USD',
        'XRP': 'XRP-USD',
        'DOGE': 'DOGE-USD',
    }
    
    symbol = symbol_map.get(ticker.upper(), f"{ticker.upper()}-USD")
    
    try:
        # Try crypto provider first
        result = _obb.crypto.price.historical(
            symbol=symbol,
            provider="yfinance",
            start_date=(datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d'),
            end_date=datetime.now().strftime('%Y-%m-%d')
        )
        if result and hasattr(result, 'results') and result.results:
            # Get most recent close price
            latest = result.results[-1]
            price = getattr(latest, 'close', None)
            if price:
                return float(price)
    except Exception as e:
        logger.debug(f"OpenBB crypto price failed for {ticker}: {e}")
    
    return None


def get_historical_prices(ticker: str, days: int = 200, asset_type: str = "stock") -> List[float]:
    """
    Get historical closing prices for SMA calculations.
    
    Args:
        ticker: Symbol (e.g., 'AAPL', 'BTC')
        days: Number of days of history (default 200)
        asset_type: 'stock' or 'crypto'
    
    Returns:
        List of closing prices (oldest to newest), empty list on failure
    """
    if not _openbb_available:
        return []
    
    start_date = (datetime.now() - timedelta(days=days + 10)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    try:
        if asset_type == "crypto":
            # Crypto symbols need -USD suffix
            symbol_map = {
                'BTC': 'BTC-USD', 'ETH': 'ETH-USD', 'SOL': 'SOL-USD',
                'ADA': 'ADA-USD', 'DOGE': 'DOGE-USD', 'DOT': 'DOT-USD',
                'AVAX': 'AVAX-USD', 'LINK': 'LINK-USD', 'MATIC': 'MATIC-USD',
                'XRP': 'XRP-USD',
            }
            symbol = symbol_map.get(ticker.upper(), f"{ticker.upper()}-USD")
            
            result = _obb.crypto.price.historical(
                symbol=symbol,
                provider="yfinance",
                start_date=start_date,
                end_date=end_date
            )
        else:
            result = _obb.equity.price.historical(
                symbol=ticker,
                provider="yfinance",
                start_date=start_date,
                end_date=end_date
            )
        
        if result and hasattr(result, 'results') and result.results:
            prices = [float(r.close) for r in result.results if hasattr(r, 'close') and r.close]
            return prices
            
    except Exception as e:
        logger.debug(f"OpenBB historical prices failed for {ticker}: {e}")
    
    return []


def get_stock_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get stock fundamental data (optional, for future use).
    
    Args:
        ticker: Stock symbol
    
    Returns:
        Dict with fundamental metrics, or None
    """
    if not _openbb_available:
        return None
    
    try:
        result = _obb.equity.fundamental.overview(ticker, provider="yfinance")
        if result and hasattr(result, 'results') and result.results:
            data = result.results[0]
            return {
                'market_cap': getattr(data, 'market_cap', None),
                'pe_ratio': getattr(data, 'pe_ratio', None),
                'eps': getattr(data, 'eps', None),
                'beta': getattr(data, 'beta', None),
                'dividend_yield': getattr(data, 'dividend_yield', None),
                'sector': getattr(data, 'sector', None),
                'industry': getattr(data, 'industry', None),
            }
    except Exception as e:
        logger.debug(f"OpenBB fundamentals failed for {ticker}: {e}")
    
    return None
