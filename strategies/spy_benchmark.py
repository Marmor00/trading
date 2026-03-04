"""
SPY Benchmark: passive buy-and-hold strategy.

Buys SPY on day 1 with all capital and holds indefinitely.
This is the reference point -- if no strategy beats this,
it's better to just buy an index fund.
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class SpyBenchmarkStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [ProfileConfig(
            profile_id='spy_benchmark',
            display_name='SPY Buy & Hold',
            description='Passive benchmark: buy SPY on day 1, hold forever. '
                        'If no strategy beats this, just buy an index fund.',
            asset_type=AssetType.ETF,
            data_source='none',
            initial_capital=10000.0,
            position_size_pct=99.0,  # All-in
            max_positions=1,
            stop_loss_pct=-99.0,     # Never trigger
            take_profit_pct=999.0,   # Never trigger
            max_holding_days=99999,  # Hold indefinitely
            commission=0.0,          # Most brokers: zero commission on ETFs
            schedule='weekdays',
        )]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        # Only buy once -- if we don't have a position yet
        if active_positions:
            return []

        return [Signal(
            ticker='SPY',
            signal_type=SignalType.BUY,
            asset_type=AssetType.ETF,
            confidence=1.0,
            reason='Benchmark: initial buy',
            metadata={
                'company_name': 'SPDR S&P 500 ETF Trust',
                'owner_name': 'BENCHMARK',
                'title': 'PASSIVE',
                'trade_date': '',
            },
        )]


register_strategy(SpyBenchmarkStrategy())
