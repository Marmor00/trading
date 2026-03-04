"""
Technical indicators library.

All functions are pure: take price arrays (List[float], newest last),
return computed values. No API calls, no I/O, no side effects.
"""

from typing import List, Dict, Optional


def sma(prices: List[float], period: int) -> Optional[float]:
    """Simple Moving Average. Returns None if not enough data."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def ema(prices: List[float], period: int) -> Optional[float]:
    """Exponential Moving Average. Returns None if not enough data."""
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_val = sum(prices[:period]) / period  # seed with SMA
    for price in prices[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val
    return ema_val


def rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Relative Strength Index (0-100). Returns None if not enough data.

    RSI measures speed and magnitude of price changes.
    Below 30 = oversold (price may bounce up).
    Above 70 = overbought (price may drop).
    """
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict]:
    """MACD indicator.

    MACD tracks momentum using the difference between two moving averages.
    A bullish crossover (MACD crosses above signal) suggests upward momentum.
    A bearish crossover (MACD crosses below signal) suggests downward momentum.

    Returns dict with macd_line, signal_line, histogram, crossover_up, crossover_down.
    """
    if len(prices) < slow + signal:
        return None

    # Calculate MACD line series
    macd_series = []
    for i in range(slow, len(prices) + 1):
        ef = ema(prices[:i], fast)
        es = ema(prices[:i], slow)
        if ef is not None and es is not None:
            macd_series.append(ef - es)

    if len(macd_series) < signal:
        return None

    macd_line = macd_series[-1]
    signal_line = ema(macd_series, signal)
    if signal_line is None:
        return None

    histogram = macd_line - signal_line

    # Crossover detection (exact: today only)
    prev_macd = macd_series[-2] if len(macd_series) >= 2 else None
    prev_signal = ema(macd_series[:-1], signal) if len(macd_series) >= signal + 1 else None

    crossover_up = False
    crossover_down = False
    if prev_macd is not None and prev_signal is not None:
        crossover_up = prev_macd <= prev_signal and macd_line > signal_line
        crossover_down = prev_macd >= prev_signal and macd_line < signal_line

    # Recent crossover (within last 10 bars / ~2 weeks) — catches signals missed by exact-day check
    recent_crossover_up = crossover_up
    recent_crossover_down = crossover_down
    lookback = min(11, len(macd_series) - signal + 1)
    if lookback >= 2:
        recent_hists = []
        for k in range(lookback):
            idx = len(macd_series) - lookback + k + 1
            sl = ema(macd_series[:idx], signal)
            if sl is not None:
                recent_hists.append(macd_series[idx - 1] - sl)
        for j in range(1, len(recent_hists)):
            if recent_hists[j - 1] <= 0 and recent_hists[j] > 0:
                recent_crossover_up = True
            if recent_hists[j - 1] >= 0 and recent_hists[j] < 0:
                recent_crossover_down = True

    return {
        'macd_line': macd_line,
        'signal_line': signal_line,
        'histogram': histogram,
        'crossover_up': crossover_up,
        'crossover_down': crossover_down,
        'recent_crossover_up': recent_crossover_up,
        'recent_crossover_down': recent_crossover_down,
        'bullish': histogram > 0,
    }


def bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2.0) -> Optional[Dict]:
    """Bollinger Bands.

    Bands show volatility around a moving average.
    Price near lower band = potentially oversold (mean reversion opportunity).
    Price near upper band = potentially overbought.
    pct_b: 0 = at lower band, 1 = at upper band.

    Returns dict with upper, middle, lower, std, pct_b.
    """
    if len(prices) < period:
        return None
    recent = prices[-period:]
    middle = sum(recent) / period
    variance = sum((p - middle) ** 2 for p in recent) / period
    std = variance ** 0.5
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)
    current = prices[-1]
    pct_b = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower,
        'std': std,
        'pct_b': pct_b,
    }


def sma_crossover(prices: List[float], fast_period: int = 50, slow_period: int = 200) -> Optional[Dict]:
    """SMA crossover detection.

    Golden cross (fast SMA crosses above slow SMA) = bullish long-term signal.
    Death cross (fast SMA crosses below slow SMA) = bearish signal.

    Returns dict with fast_sma, slow_sma, golden_cross, death_cross, bullish.
    """
    if len(prices) < slow_period + 1:
        return None
    fast_now = sma(prices, fast_period)
    slow_now = sma(prices, slow_period)
    fast_prev = sma(prices[:-1], fast_period)
    slow_prev = sma(prices[:-1], slow_period)
    if any(v is None for v in [fast_now, slow_now, fast_prev, slow_prev]):
        return None

    golden_cross = fast_prev <= slow_prev and fast_now > slow_now
    death_cross = fast_prev >= slow_prev and fast_now < slow_now

    # Recent crossover (within last 10 days / ~2 weeks) — SMA crosses are rare
    recent_golden = golden_cross
    recent_death = death_cross
    diffs = []
    for offset in range(min(11, len(prices) - slow_period)):
        end = len(prices) - offset
        f = sma(prices[:end], fast_period)
        s = sma(prices[:end], slow_period)
        if f is not None and s is not None:
            diffs.append(f - s)
        else:
            break
    # diffs[0] = today, diffs[1] = yesterday, etc.
    for i in range(len(diffs) - 1):
        if diffs[i] > 0 and diffs[i + 1] <= 0:
            recent_golden = True
        if diffs[i] < 0 and diffs[i + 1] >= 0:
            recent_death = True

    return {
        'fast_sma': fast_now,
        'slow_sma': slow_now,
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'recent_golden_cross': recent_golden,
        'recent_death_cross': recent_death,
        'bullish': fast_now > slow_now,
    }


def week52_position(prices: List[float]) -> Optional[Dict]:
    """52-week high/low position.

    Shows where the current price sits relative to its annual range.
    Near 0% = near 52-week low (deep value territory).
    Near 100% = near 52-week high (momentum/breakout territory).

    Returns dict with high_52w, low_52w, current, pct_from_high, pct_from_low, position.
    """
    if len(prices) < 200:
        return None
    prices_252 = prices[-252:] if len(prices) >= 252 else prices
    high = max(prices_252)
    low = min(prices_252)
    current = prices[-1]
    return {
        'high_52w': high,
        'low_52w': low,
        'current': current,
        'pct_from_high': ((current - high) / high) * 100,
        'pct_from_low': ((current - low) / low) * 100,
        'position': (current - low) / (high - low) * 100 if (high - low) > 0 else 50,
    }
