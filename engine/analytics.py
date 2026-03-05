"""
Advanced trading metrics: Sharpe Ratio, Max Drawdown, Profit Factor, Sortino Ratio.
"""

import math
from typing import List, Dict, Optional


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> Optional[float]:
    """
    Calculate Sharpe Ratio.
    
    Sharpe = (mean(returns) - risk_free_rate) / std(returns)
    
    Args:
        returns: List of periodic returns (e.g., daily % returns)
        risk_free_rate: Risk-free rate (default 0 for simplicity)
    
    Returns:
        Sharpe ratio or None if insufficient data
    """
    if not returns or len(returns) < 2:
        return None
    
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)
    
    if std_dev == 0:
        return None
    
    sharpe = (mean_return - risk_free_rate) / std_dev
    return round(sharpe, 4)


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """
    Calculate Maximum Drawdown (peak-to-trough).
    
    Args:
        equity_curve: List of portfolio values over time
    
    Returns:
        Max drawdown as a negative percentage (e.g., -15.5 means 15.5% drawdown)
    """
    if not equity_curve or len(equity_curve) < 2:
        return 0.0
    
    peak = equity_curve[0]
    max_drawdown = 0.0
    
    for value in equity_curve:
        if value > peak:
            peak = value
        
        if peak > 0:
            drawdown = ((value - peak) / peak) * 100
            if drawdown < max_drawdown:
                max_drawdown = drawdown
    
    return round(max_drawdown, 2)


def calculate_profit_factor(winning_trades: List[float], losing_trades: List[float]) -> Optional[float]:
    """
    Calculate Profit Factor.
    
    Profit Factor = Sum of Wins / |Sum of Losses|
    
    Args:
        winning_trades: List of positive returns (profits)
        losing_trades: List of negative returns (losses)
    
    Returns:
        Profit factor or None if no losses
    """
    total_wins = sum(abs(w) for w in winning_trades) if winning_trades else 0
    total_losses = sum(abs(l) for l in losing_trades) if losing_trades else 0
    
    if total_losses == 0:
        return None if total_wins == 0 else float('inf')
    
    return round(total_wins / total_losses, 2)


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.0, 
                            target_return: float = 0.0) -> Optional[float]:
    """
    Calculate Sortino Ratio.
    
    Like Sharpe but only penalizes downside volatility.
    Sortino = (mean(returns) - target_return) / downside_std
    
    Args:
        returns: List of periodic returns
        risk_free_rate: Risk-free rate (unused, kept for API consistency)
        target_return: Minimum acceptable return (default 0)
    
    Returns:
        Sortino ratio or None if insufficient data
    """
    if not returns or len(returns) < 2:
        return None
    
    mean_return = sum(returns) / len(returns)
    
    # Downside returns (only negative deviations from target)
    downside_returns = [min(0, r - target_return) for r in returns]
    downside_squared = [d ** 2 for d in downside_returns]
    
    if not downside_squared:
        return None
    
    downside_variance = sum(downside_squared) / len(downside_squared)
    downside_std = math.sqrt(downside_variance)
    
    if downside_std == 0:
        return None
    
    sortino = (mean_return - target_return) / downside_std
    return round(sortino, 4)


def calculate_all_metrics(equity_curve: List[float], 
                          closed_trades: List[Dict]) -> Dict[str, Optional[float]]:
    """
    Calculate all advanced metrics from equity curve and trade history.
    
    Args:
        equity_curve: List of portfolio total values over time
        closed_trades: List of dicts with 'return_pct' key
    
    Returns:
        Dict with sharpe_ratio, max_drawdown, profit_factor, sortino_ratio
    """
    # Calculate periodic returns from equity curve
    returns = []
    for i in range(1, len(equity_curve)):
        if equity_curve[i-1] > 0:
            ret = ((equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]) * 100
            returns.append(ret)
    
    # Split trades into winners and losers
    winning_trades = []
    losing_trades = []
    for trade in closed_trades:
        ret = trade.get('return_pct', 0) or 0
        if ret > 0:
            winning_trades.append(ret)
        elif ret < 0:
            losing_trades.append(ret)
    
    return {
        'sharpe_ratio': calculate_sharpe_ratio(returns),
        'max_drawdown': calculate_max_drawdown(equity_curve),
        'profit_factor': calculate_profit_factor(winning_trades, losing_trades),
        'sortino_ratio': calculate_sortino_ratio(returns),
    }
