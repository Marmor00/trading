#!/usr/bin/env python3
"""
CLI script to run backtests on trading strategy profiles.

Usage:
    python scripts/run_backtest.py --profile score_70 --years 3
    python scripts/run_backtest.py --profile rsi_oversold_mega --ticker AAPL --years 5
    python scripts/run_backtest.py --all --years 3
    python scripts/run_backtest.py --list
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

from engine.backtester import (
    backtest_strategy,
    backtest_profile,
    backtest_all_profiles,
    generate_report,
    get_benchmark_returns,
    PROFILE_TICKERS,
    STRATEGY_MAPPING,
)
from strategies.registry import get_all_profiles, get_profile


def list_profiles():
    """List all available profiles and their backtest support."""
    print("\nAvailable Profiles:")
    print("-" * 70)
    print(f"{'Profile ID':<25} {'Name':<30} {'Backtest Support':<15}")
    print("-" * 70)
    
    profiles = get_all_profiles()
    for strategy, profile in profiles:
        has_strategy = "✓ Full" if profile.profile_id in STRATEGY_MAPPING else "○ Fallback"
        print(f"{profile.profile_id:<25} {profile.display_name:<30} {has_strategy:<15}")
    
    print("-" * 70)
    print(f"\nTotal: {len(profiles)} profiles")
    print("✓ Full = Dedicated backtesting strategy")
    print("○ Fallback = Uses generic RSI strategy (limited accuracy)")
    print()


def run_single_ticker_backtest(args):
    """Run backtest for a single profile on a single ticker."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.years * 365)
    
    print(f"\n{'='*60}")
    print(f"BACKTEST: {args.profile} on {args.ticker}")
    print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({args.years} years)")
    print(f"{'='*60}\n")
    
    result = backtest_strategy(
        profile_id=args.profile,
        ticker=args.ticker,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        initial_capital=args.capital,
    )
    
    if 'error' in result:
        print(f"ERROR: {result['error']}")
        return 1
    
    print_single_result(result)
    
    # Compare with benchmark
    benchmark = get_benchmark_returns(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
    )
    print_benchmark_comparison(result, benchmark)
    
    return 0


def run_profile_backtest(args):
    """Run backtest for a profile across its ticker universe."""
    print(f"\n{'='*60}")
    print(f"BACKTEST: {args.profile} (Multi-Ticker)")
    print(f"Period: {args.years} years | Capital: ${args.capital:,.0f}")
    print(f"{'='*60}\n")
    
    result = backtest_profile(
        profile_id=args.profile,
        years=args.years,
        initial_capital=args.capital,
    )
    
    if 'error' in result:
        print(f"ERROR: {result['error']}")
        return 1
    
    print_profile_result(result)
    
    # Compare with benchmark
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.years * 365)
    benchmark = get_benchmark_returns(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
    )
    print_profile_benchmark(result, benchmark)
    
    return 0


def run_all_backtests(args):
    """Run backtests for all profiles."""
    print(f"\n{'='*60}")
    print(f"BACKTEST: ALL PROFILES")
    print(f"Period: {args.years} years | Capital: ${args.capital:,.0f}")
    print(f"{'='*60}\n")
    
    results = backtest_all_profiles(years=args.years, initial_capital=args.capital)
    
    if not results:
        print("No successful backtests completed.")
        return 1
    
    # Get benchmark for period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.years * 365)
    benchmark = get_benchmark_returns(
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d'),
    )
    
    report = generate_report(results, benchmark)
    print(report)
    
    # Summary statistics
    print_summary(results, benchmark)
    
    return 0


def print_single_result(result):
    """Print results for a single ticker backtest."""
    print("RESULTS:")
    print("-" * 40)
    print(f"  Profile:           {result['profile_name']}")
    print(f"  Ticker:            {result['ticker']}")
    print(f"  Period:            {result['start_date']} to {result['end_date']}")
    print(f"  Trading Days:      {result['trading_days']}")
    print()
    print("PERFORMANCE:")
    print("-" * 40)
    print(f"  Initial Capital:   ${result['initial_capital']:,.2f}")
    print(f"  Final Equity:      ${result['final_equity']:,.2f}")
    print(f"  Return:            {result['return_pct']:+.2f}%")
    print(f"  Buy & Hold Return: {result['buy_hold_return_pct']:+.2f}%")
    print()
    print("RISK METRICS:")
    print("-" * 40)
    print(f"  Sharpe Ratio:      {result['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio:     {result['sortino_ratio']:.2f}")
    print(f"  Max Drawdown:      {result['max_drawdown_pct']:.2f}%")
    print()
    print("TRADE STATISTICS:")
    print("-" * 40)
    print(f"  Number of Trades:  {result['num_trades']}")
    print(f"  Win Rate:          {result['win_rate']:.1f}%")
    print(f"  Profit Factor:     {result['profit_factor']:.2f}")
    print(f"  Avg Trade:         {result['avg_trade_pct']:+.2f}%")
    print(f"  Best Trade:        {result['best_trade_pct']:+.2f}%")
    print(f"  Worst Trade:       {result['worst_trade_pct']:+.2f}%")
    print(f"  Exposure Time:     {result['exposure_time_pct']:.1f}%")
    print()


def print_benchmark_comparison(result, benchmark):
    """Print comparison with benchmark."""
    print("VS BENCHMARK (SPY):")
    print("-" * 40)
    spy_return = benchmark.get('return_pct', 0)
    strategy_return = result['return_pct']
    alpha = strategy_return - spy_return
    
    print(f"  SPY Return:        {spy_return:+.2f}%")
    print(f"  Strategy Return:   {strategy_return:+.2f}%")
    print(f"  Alpha:             {alpha:+.2f}%")
    
    if alpha > 0:
        print(f"  ✓ Strategy OUTPERFORMS benchmark by {alpha:.1f}%")
    else:
        print(f"  ✗ Strategy UNDERPERFORMS benchmark by {abs(alpha):.1f}%")
    print()


def print_profile_result(result):
    """Print results for a multi-ticker profile backtest."""
    print("AGGREGATE RESULTS:")
    print("-" * 50)
    print(f"  Profile:           {result['profile_name']}")
    print(f"  Period:            {result['start_date']} to {result['end_date']} ({result['years']} years)")
    print(f"  Tickers Tested:    {result['tickers_tested']}/{result['tickers_total']}")
    print()
    print("AVERAGE PERFORMANCE ACROSS ALL TICKERS:")
    print("-" * 50)
    print(f"  Avg Return:        {result['avg_return_pct']:+.2f}%")
    print(f"  Median Return:     {result['median_return_pct']:+.2f}%")
    print(f"  Avg Buy & Hold:    {result['avg_buy_hold_pct']:+.2f}%")
    print()
    print("RISK METRICS (AVERAGED):")
    print("-" * 50)
    print(f"  Avg Sharpe Ratio:  {result['avg_sharpe_ratio']:.2f}")
    print(f"  Avg Sortino Ratio: {result['avg_sortino_ratio']:.2f}")
    print(f"  Avg Max Drawdown:  {result['avg_max_drawdown_pct']:.2f}%")
    print()
    print("TRADE STATISTICS:")
    print("-" * 50)
    print(f"  Total Trades:      {result['total_trades']}")
    print(f"  Avg Trades/Ticker: {result['avg_trades_per_ticker']:.1f}")
    print(f"  Avg Win Rate:      {result['avg_win_rate']:.1f}%")
    print(f"  Avg Profit Factor: {result['avg_profit_factor']:.2f}")
    print()
    
    # Individual ticker results
    print("INDIVIDUAL TICKER RESULTS:")
    print("-" * 50)
    print(f"{'Ticker':<8} {'Return%':>10} {'B&H%':>10} {'Sharpe':>8} {'MaxDD%':>8} {'Trades':>7}")
    print("-" * 50)
    for r in sorted(result['individual_results'], key=lambda x: x['return_pct'], reverse=True):
        print(f"{r['ticker']:<8} {r['return_pct']:>+10.2f} {r['buy_hold_return_pct']:>+10.2f} "
              f"{r['sharpe_ratio']:>8.2f} {r['max_drawdown_pct']:>8.2f} {r['num_trades']:>7}")
    print()


def print_profile_benchmark(result, benchmark):
    """Print profile vs benchmark comparison."""
    print("VS BENCHMARK (SPY):")
    print("-" * 50)
    spy_return = benchmark.get('return_pct', 0)
    strategy_return = result['avg_return_pct']
    alpha = strategy_return - spy_return
    
    print(f"  SPY Return:        {spy_return:+.2f}%")
    print(f"  Avg Strategy:      {strategy_return:+.2f}%")
    print(f"  Alpha:             {alpha:+.2f}%")
    
    if result['outperforms_buy_hold']:
        print(f"  ✓ Strategy OUTPERFORMS buy & hold (internal comparison)")
    else:
        print(f"  ✗ Strategy UNDERPERFORMS buy & hold (internal comparison)")
    print()


def print_summary(results, benchmark):
    """Print summary of all profile backtests."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    spy_return = benchmark.get('return_pct', 0)
    
    # Count outperformers
    outperformers = [r for r in results if r['avg_return_pct'] > spy_return]
    positive_alpha = [r for r in results if r.get('outperforms_buy_hold')]
    
    print(f"\nTotal Profiles Tested: {len(results)}")
    print(f"Outperform SPY ({spy_return:.1f}%): {len(outperformers)}/{len(results)}")
    print(f"Beat Buy & Hold (per ticker): {len(positive_alpha)}/{len(results)}")
    
    if results:
        print(f"\nBest Performing Profile:")
        best = results[0]
        print(f"  {best['profile_name']}: {best['avg_return_pct']:+.2f}% avg return")
        
        worst = results[-1]
        print(f"\nWorst Performing Profile:")
        print(f"  {worst['profile_name']}: {worst['avg_return_pct']:+.2f}% avg return")
        
        # Best risk-adjusted
        by_sharpe = sorted(results, key=lambda x: x['avg_sharpe_ratio'], reverse=True)
        if by_sharpe:
            best_sharpe = by_sharpe[0]
            print(f"\nBest Risk-Adjusted (Sharpe):")
            print(f"  {best_sharpe['profile_name']}: Sharpe {best_sharpe['avg_sharpe_ratio']:.2f}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Run backtests on Trading Simulation Lab strategy profiles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --profile rsi_oversold_mega --years 3
  %(prog)s --profile macd_cross_etf --ticker QQQ --years 5
  %(prog)s --all --years 3
  %(prog)s --list
        """
    )
    
    parser.add_argument('--profile', '-p', type=str, help='Profile ID to backtest')
    parser.add_argument('--ticker', '-t', type=str, help='Specific ticker to test (single ticker mode)')
    parser.add_argument('--years', '-y', type=int, default=3, help='Number of years to backtest (default: 3)')
    parser.add_argument('--capital', '-c', type=float, default=10000.0, help='Initial capital (default: 10000)')
    parser.add_argument('--all', '-a', action='store_true', help='Backtest all profiles')
    parser.add_argument('--list', '-l', action='store_true', help='List available profiles')
    
    args = parser.parse_args()
    
    # Handle --list
    if args.list:
        list_profiles()
        return 0
    
    # Handle --all
    if args.all:
        return run_all_backtests(args)
    
    # Handle single profile
    if args.profile:
        # Validate profile exists
        if not get_profile(args.profile):
            print(f"ERROR: Profile '{args.profile}' not found.")
            print("Use --list to see available profiles.")
            return 1
        
        # Single ticker or multi-ticker?
        if args.ticker:
            return run_single_ticker_backtest(args)
        else:
            return run_profile_backtest(args)
    
    # No arguments - show help
    parser.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
