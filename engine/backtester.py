"""
Backtesting module using backtesting.py library.

This module adapts existing forward-testing strategies to backtest against
historical data, providing validation metrics without modifying core strategies.
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

from backtesting import Backtest, Strategy
from backtesting.lib import crossover

from strategies.registry import get_profile, get_all_profiles
from engine.models import ProfileConfig, AssetType


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_historical_data(
    ticker: str,
    start_date: str,
    end_date: str,
    interval: str = '1d'
) -> pd.DataFrame:
    """Fetch OHLCV data from Yahoo Finance for backtesting.py format.
    
    Returns DataFrame with columns: Open, High, Low, Close, Volume
    """
    stock = yf.Ticker(ticker)
    df = stock.history(start=start_date, end=end_date, interval=interval)
    
    if df.empty:
        raise ValueError(f"No data available for {ticker} between {start_date} and {end_date}")
    
    # backtesting.py expects these exact column names
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    df.index = pd.to_datetime(df.index)
    
    # Remove timezone info if present
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    
    return df


def get_benchmark_returns(start_date: str, end_date: str, ticker: str = 'SPY') -> Dict:
    """Get buy-and-hold returns for a benchmark."""
    try:
        df = fetch_historical_data(ticker, start_date, end_date)
        if df.empty or len(df) < 2:
            return {'return_pct': 0, 'start_price': 0, 'end_price': 0}
        
        start_price = df['Close'].iloc[0]
        end_price = df['Close'].iloc[-1]
        return_pct = ((end_price - start_price) / start_price) * 100
        
        return {
            'ticker': ticker,
            'return_pct': return_pct,
            'start_price': start_price,
            'end_price': end_price,
            'start_date': df.index[0].strftime('%Y-%m-%d'),
            'end_date': df.index[-1].strftime('%Y-%m-%d'),
        }
    except Exception as e:
        print(f"Warning: Could not fetch benchmark {ticker}: {e}")
        return {'return_pct': 0, 'start_price': 0, 'end_price': 0}


# =============================================================================
# TECHNICAL INDICATORS FOR BACKTESTING
# =============================================================================

def SMA(data: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average."""
    return data.rolling(window=period).mean()


def RSI(data: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def MACD(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD indicator. Returns (macd_line, signal_line, histogram)."""
    ema_fast = data.ewm(span=fast, adjust=False).mean()
    ema_slow = data.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def BollingerBands(data: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands. Returns (upper, middle, lower)."""
    middle = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower


def PercentB(data: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """Bollinger %B indicator (0-1 range, <0 below lower band, >1 above upper)."""
    upper, middle, lower = BollingerBands(data, period, std_dev)
    return (data - lower) / (upper - lower)


# =============================================================================
# STRATEGY ADAPTERS
# =============================================================================

class RSIOversoldStrategy(Strategy):
    """RSI Oversold Strategy for backtesting.py."""
    
    # Parameters (can be optimized)
    rsi_period = 14
    rsi_buy_threshold = 35
    rsi_sell_threshold = 70
    stop_loss_pct = 8
    take_profit_pct = 15
    
    def init(self):
        self.rsi = self.I(RSI, pd.Series(self.data.Close), self.rsi_period)
    
    def next(self):
        if not self.position:
            if self.rsi[-1] < self.rsi_buy_threshold:
                self.buy(sl=self.data.Close[-1] * (1 - self.stop_loss_pct/100),
                         tp=self.data.Close[-1] * (1 + self.take_profit_pct/100))
        else:
            if self.rsi[-1] > self.rsi_sell_threshold:
                self.position.close()


class MACDCrossoverStrategy(Strategy):
    """MACD Crossover Strategy for backtesting.py."""
    
    fast_period = 12
    slow_period = 26
    signal_period = 9
    stop_loss_pct = 7
    take_profit_pct = 12
    
    def init(self):
        close = pd.Series(self.data.Close)
        macd_line, signal_line, histogram = MACD(close, self.fast_period, self.slow_period, self.signal_period)
        self.macd = self.I(lambda: macd_line, name='MACD')
        self.signal = self.I(lambda: signal_line, name='Signal')
    
    def next(self):
        if not self.position:
            if crossover(self.macd, self.signal):
                self.buy(sl=self.data.Close[-1] * (1 - self.stop_loss_pct/100),
                         tp=self.data.Close[-1] * (1 + self.take_profit_pct/100))
        else:
            if crossover(self.signal, self.macd):
                self.position.close()


class BollingerBounceStrategy(Strategy):
    """Bollinger Band Bounce Strategy for backtesting.py."""
    
    bb_period = 20
    bb_std = 2.0
    pct_b_buy = 0.20
    pct_b_sell = 0.95
    stop_loss_pct = 6
    take_profit_pct = 10
    
    def init(self):
        close = pd.Series(self.data.Close)
        self.pct_b = self.I(PercentB, close, self.bb_period, self.bb_std)
    
    def next(self):
        if not self.position:
            if self.pct_b[-1] < self.pct_b_buy:
                self.buy(sl=self.data.Close[-1] * (1 - self.stop_loss_pct/100),
                         tp=self.data.Close[-1] * (1 + self.take_profit_pct/100))
        else:
            if self.pct_b[-1] > self.pct_b_sell:
                self.position.close()


class GoldenCrossStrategy(Strategy):
    """SMA 50/200 Golden Cross Strategy for backtesting.py."""
    
    fast_sma = 50
    slow_sma = 200
    stop_loss_pct = 10
    take_profit_pct = 20
    
    def init(self):
        close = pd.Series(self.data.Close)
        self.sma_fast = self.I(SMA, close, self.fast_sma)
        self.sma_slow = self.I(SMA, close, self.slow_sma)
    
    def next(self):
        if not self.position:
            if crossover(self.sma_fast, self.sma_slow):
                self.buy(sl=self.data.Close[-1] * (1 - self.stop_loss_pct/100),
                         tp=self.data.Close[-1] * (1 + self.take_profit_pct/100))
        else:
            if crossover(self.sma_slow, self.sma_fast):
                self.position.close()


class Week52LowStrategy(Strategy):
    """52-Week Low Strategy for backtesting.py."""
    
    lookback = 252  # ~1 year of trading days
    position_threshold = 25  # Buy when price is in bottom 25% of range
    exit_threshold = 85
    stop_loss_pct = 12
    take_profit_pct = 25
    
    def init(self):
        pass  # Calculate in next() to handle rolling window
    
    def next(self):
        if len(self.data.Close) < self.lookback:
            return
        
        window = list(self.data.Close[-self.lookback:])
        high_52w = max(window)
        low_52w = min(window)
        current = self.data.Close[-1]
        
        if high_52w == low_52w:
            return
        
        position_pct = ((current - low_52w) / (high_52w - low_52w)) * 100
        
        if not self.position:
            if position_pct <= self.position_threshold:
                self.buy(sl=current * (1 - self.stop_loss_pct/100),
                         tp=current * (1 + self.take_profit_pct/100))
        else:
            if position_pct >= self.exit_threshold:
                self.position.close()


class RSIBBComboStrategy(Strategy):
    """RSI + Bollinger Bands Combo Strategy for backtesting.py."""
    
    rsi_period = 14
    rsi_threshold = 35
    bb_period = 20
    bb_std = 2.0
    pct_b_threshold = 0.15
    sell_rsi_threshold = 65
    stop_loss_pct = 7
    take_profit_pct = 12
    
    def init(self):
        close = pd.Series(self.data.Close)
        self.rsi = self.I(RSI, close, self.rsi_period)
        self.pct_b = self.I(PercentB, close, self.bb_period, self.bb_std)
    
    def next(self):
        if not self.position:
            if self.rsi[-1] < self.rsi_threshold and self.pct_b[-1] < self.pct_b_threshold:
                self.buy(sl=self.data.Close[-1] * (1 - self.stop_loss_pct/100),
                         tp=self.data.Close[-1] * (1 + self.take_profit_pct/100))
        else:
            if self.rsi[-1] > self.sell_rsi_threshold:
                self.position.close()


# =============================================================================
# PROFILE TO STRATEGY MAPPING
# =============================================================================

# Map profile IDs to backtesting strategy classes
STRATEGY_MAPPING = {
    # RSI profiles
    'rsi_oversold_mega': RSIOversoldStrategy,
    'rsi_oversold_growth': RSIOversoldStrategy,
    
    # MACD profiles  
    'macd_cross_mega': MACDCrossoverStrategy,
    'macd_cross_growth': MACDCrossoverStrategy,
    'macd_cross_etf': MACDCrossoverStrategy,
    
    # Bollinger profiles
    'bband_bounce_mega': BollingerBounceStrategy,
    'bband_bounce_etf': BollingerBounceStrategy,
    
    # SMA profiles
    'golden_cross_mega': GoldenCrossStrategy,
    
    # 52-week profiles
    'w52_low_mega': Week52LowStrategy,
    
    # Combo profiles
    'rsi_bb_combo_mega': RSIBBComboStrategy,
}

# Default tickers per profile for multi-ticker backtesting
PROFILE_TICKERS = {
    'rsi_oversold_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'rsi_oversold_growth': ['AMD', 'CRM', 'NFLX', 'SQ', 'PLTR', 'UBER'],
    'macd_cross_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'macd_cross_growth': ['AMD', 'CRM', 'NFLX', 'SQ', 'PLTR', 'UBER'],
    'macd_cross_etf': ['QQQ', 'IWM', 'DIA', 'GLD', 'XBI', 'TLT'],
    'bband_bounce_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'bband_bounce_etf': ['QQQ', 'IWM', 'DIA', 'GLD', 'XBI', 'TLT'],
    'golden_cross_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'w52_low_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    'rsi_bb_combo_mega': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM'],
    # OpenInsider profiles (use same mega-cap universe for testing)
    'score_60': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'],
    'score_70': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'],
    'score_80': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'],
}


def get_strategy_for_profile(profile_id: str) -> Optional[type]:
    """Get the backtesting Strategy class for a profile."""
    return STRATEGY_MAPPING.get(profile_id)


def configure_strategy_from_profile(strategy_class: type, profile: ProfileConfig) -> Dict:
    """Extract strategy parameters from a profile config."""
    params = {}
    extra = profile.extra_params
    
    # Common parameters
    params['stop_loss_pct'] = abs(profile.stop_loss_pct)
    params['take_profit_pct'] = profile.take_profit_pct
    
    # Profile-specific parameters
    if 'rsi' in profile.profile_id or 'rsi' in extra.get('indicator', ''):
        if 'buy_threshold' in extra:
            params['rsi_buy_threshold'] = extra['buy_threshold']
        if 'sell_threshold' in extra:
            params['rsi_sell_threshold'] = extra['sell_threshold']
    
    if 'bb' in profile.profile_id or extra.get('indicator') == 'bollinger':
        if 'buy_threshold' in extra:
            params['pct_b_buy'] = extra['buy_threshold']
        if 'sell_threshold' in extra:
            params['pct_b_sell'] = extra['sell_threshold']
    
    if 'w52' in profile.profile_id:
        if 'buy_threshold' in extra:
            params['position_threshold'] = extra['buy_threshold']
        if 'sell_threshold' in extra:
            params['exit_threshold'] = extra['sell_threshold']
    
    return params


# =============================================================================
# MAIN BACKTESTING FUNCTIONS
# =============================================================================

def backtest_strategy(
    profile_id: str,
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 10000.0,
    commission: float = 0.001,
) -> Dict:
    """Run a backtest for a single profile on a single ticker.
    
    Args:
        profile_id: The profile to backtest
        ticker: Stock/ETF ticker symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        initial_capital: Starting capital
        commission: Commission as decimal (0.001 = 0.1%)
    
    Returns:
        Dictionary with performance metrics
    """
    # Get profile config
    result = get_profile(profile_id)
    if not result:
        return {'error': f'Profile {profile_id} not found'}
    
    strategy_instance, profile = result
    
    # Get strategy class
    strategy_class = get_strategy_for_profile(profile_id)
    if not strategy_class:
        # Try a generic RSI strategy as fallback for non-technical profiles
        print(f"  No specific strategy for {profile_id}, using RSIOversoldStrategy as fallback")
        strategy_class = RSIOversoldStrategy
    
    # Fetch data
    try:
        data = fetch_historical_data(ticker, start_date, end_date)
    except Exception as e:
        return {'error': f'Failed to fetch data: {e}'}
    
    if len(data) < 50:
        return {'error': f'Insufficient data for {ticker}: {len(data)} days'}
    
    # Configure strategy parameters from profile
    params = configure_strategy_from_profile(strategy_class, profile)
    
    # Create a dynamic subclass with the configured parameters
    configured_strategy = type(
        f'{strategy_class.__name__}_{profile_id}',
        (strategy_class,),
        params
    )
    
    # Run backtest
    bt = Backtest(
        data,
        configured_strategy,
        cash=initial_capital,
        commission=commission,
        exclusive_orders=True,
        trade_on_close=True,
    )
    
    stats = bt.run()
    
    # Extract metrics
    return {
        'profile_id': profile_id,
        'profile_name': profile.display_name,
        'ticker': ticker,
        'start_date': data.index[0].strftime('%Y-%m-%d'),
        'end_date': data.index[-1].strftime('%Y-%m-%d'),
        'trading_days': len(data),
        'initial_capital': initial_capital,
        'final_equity': stats['Equity Final [$]'],
        'return_pct': stats['Return [%]'],
        'buy_hold_return_pct': stats['Buy & Hold Return [%]'],
        'sharpe_ratio': stats['Sharpe Ratio'] if not pd.isna(stats['Sharpe Ratio']) else 0,
        'sortino_ratio': stats['Sortino Ratio'] if not pd.isna(stats['Sortino Ratio']) else 0,
        'max_drawdown_pct': stats['Max. Drawdown [%]'],
        'win_rate': stats['Win Rate [%]'] if not pd.isna(stats['Win Rate [%]']) else 0,
        'profit_factor': stats['Profit Factor'] if not pd.isna(stats['Profit Factor']) else 0,
        'num_trades': stats['# Trades'],
        'avg_trade_pct': stats['Avg. Trade [%]'] if not pd.isna(stats['Avg. Trade [%]']) else 0,
        'best_trade_pct': stats['Best Trade [%]'] if not pd.isna(stats['Best Trade [%]']) else 0,
        'worst_trade_pct': stats['Worst Trade [%]'] if not pd.isna(stats['Worst Trade [%]']) else 0,
        'exposure_time_pct': stats['Exposure Time [%]'] if not pd.isna(stats['Exposure Time [%]']) else 0,
    }


def backtest_profile(
    profile_id: str,
    years: int = 3,
    initial_capital: float = 10000.0,
    commission: float = 0.001,
) -> Dict:
    """Backtest a profile across all tickers in its universe.
    
    Args:
        profile_id: The profile to backtest
        years: Number of years to backtest
        initial_capital: Starting capital per ticker
        commission: Commission as decimal
    
    Returns:
        Aggregated performance metrics across all tickers
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    tickers = PROFILE_TICKERS.get(profile_id, ['SPY'])
    
    results = []
    successful = 0
    
    for ticker in tickers:
        print(f"  Testing {profile_id} on {ticker}...")
        result = backtest_strategy(
            profile_id=profile_id,
            ticker=ticker,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            initial_capital=initial_capital,
            commission=commission,
        )
        
        if 'error' not in result:
            results.append(result)
            successful += 1
        else:
            print(f"    ! {result['error']}")
    
    if not results:
        return {'error': f'No successful backtests for {profile_id}'}
    
    # Aggregate metrics
    return {
        'profile_id': profile_id,
        'profile_name': results[0]['profile_name'],
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'years': years,
        'tickers_tested': successful,
        'tickers_total': len(tickers),
        'avg_return_pct': np.mean([r['return_pct'] for r in results]),
        'median_return_pct': np.median([r['return_pct'] for r in results]),
        'avg_buy_hold_pct': np.mean([r['buy_hold_return_pct'] for r in results]),
        'avg_sharpe_ratio': np.mean([r['sharpe_ratio'] for r in results]),
        'avg_sortino_ratio': np.mean([r['sortino_ratio'] for r in results]),
        'avg_max_drawdown_pct': np.mean([r['max_drawdown_pct'] for r in results]),
        'avg_win_rate': np.mean([r['win_rate'] for r in results]),
        'avg_profit_factor': np.mean([r['profit_factor'] for r in results]),
        'total_trades': sum(r['num_trades'] for r in results),
        'avg_trades_per_ticker': np.mean([r['num_trades'] for r in results]),
        'individual_results': results,
        'outperforms_buy_hold': np.mean([r['return_pct'] for r in results]) > np.mean([r['buy_hold_return_pct'] for r in results]),
    }


def backtest_all_profiles(
    years: int = 3,
    initial_capital: float = 10000.0,
) -> List[Dict]:
    """Backtest all registered profiles.
    
    Returns sorted list of results (best performing first).
    """
    profiles = get_all_profiles()
    all_results = []
    
    for strategy, profile in profiles:
        print(f"\nBacktesting {profile.display_name}...")
        result = backtest_profile(
            profile_id=profile.profile_id,
            years=years,
            initial_capital=initial_capital,
        )
        
        if 'error' not in result:
            all_results.append(result)
    
    # Sort by average return (best first)
    all_results.sort(key=lambda x: x['avg_return_pct'], reverse=True)
    
    return all_results


def generate_report(results: List[Dict], benchmark: Dict = None) -> str:
    """Generate a formatted text report from backtest results."""
    lines = []
    lines.append("=" * 80)
    lines.append("BACKTESTING REPORT")
    lines.append("=" * 80)
    
    if benchmark:
        lines.append(f"\nBenchmark: {benchmark.get('ticker', 'SPY')} Buy & Hold")
        lines.append(f"  Period: {benchmark.get('start_date')} to {benchmark.get('end_date')}")
        lines.append(f"  Return: {benchmark.get('return_pct', 0):.2f}%")
        lines.append("")
    
    lines.append(f"\n{'Profile':<25} {'Return%':>10} {'Sharpe':>8} {'MaxDD%':>8} {'WinRate':>8} {'Trades':>7} {'vs B&H':>8}")
    lines.append("-" * 80)
    
    for r in results:
        outperform = "✓" if r.get('outperforms_buy_hold') else "✗"
        alpha = r.get('avg_return_pct', 0) - r.get('avg_buy_hold_pct', 0)
        lines.append(
            f"{r['profile_name']:<25} "
            f"{r['avg_return_pct']:>10.2f} "
            f"{r['avg_sharpe_ratio']:>8.2f} "
            f"{r['avg_max_drawdown_pct']:>8.2f} "
            f"{r['avg_win_rate']:>7.1f}% "
            f"{r['total_trades']:>7} "
            f"{alpha:>+7.1f}%"
        )
    
    lines.append("-" * 80)
    lines.append("\nLegend: vs B&H = Alpha over Buy & Hold")
    lines.append("")
    
    return "\n".join(lines)
