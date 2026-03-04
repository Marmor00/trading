"""
Congress Trading strategy: follow stock purchases by U.S. House members.

Based on the premise that politicians with access to non-public information
tend to outperform the market. Data from House Stock Watcher (public STOCK Act filings).

Two profiles:
- congress_all: All congress purchases >= $15k
- congress_large: Only large purchases >= $50k
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class CongressTradingStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [
            ProfileConfig(
                profile_id='congress_all',
                display_name='Congress >$15k',
                description='Follow all U.S. House member stock purchases over $15,000',
                asset_type=AssetType.STOCK,
                data_source='congress',
                initial_capital=10000.0,
                position_size_pct=10,
                max_positions=10,
                stop_loss_pct=-10.0,
                take_profit_pct=20.0,
                max_holding_days=60,
                commission=6.95,
                schedule='weekdays',
                extra_params={'min_value': 15001},
            ),
            ProfileConfig(
                profile_id='congress_large',
                display_name='Congress >$50k',
                description='Follow only large U.S. House member stock purchases over $50,000',
                asset_type=AssetType.STOCK,
                data_source='congress',
                initial_capital=10000.0,
                position_size_pct=12,
                max_positions=8,
                stop_loss_pct=-10.0,
                take_profit_pct=20.0,
                max_holding_days=60,
                commission=6.95,
                schedule='weekdays',
                extra_params={'min_value': 50001},
            ),
        ]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        min_value = profile.extra_params.get('min_value', 15001)
        active_tickers = {p['ticker'] for p in active_positions}
        seen_tickers = set()
        signals = []

        for trade in market_data:
            if trade.get('min_value', 0) < min_value:
                continue

            ticker = trade['ticker']
            if ticker in active_tickers or ticker in seen_tickers:
                continue

            seen_tickers.add(ticker)
            signals.append(Signal(
                ticker=ticker,
                signal_type=SignalType.BUY,
                asset_type=AssetType.STOCK,
                confidence=min(trade.get('min_value', 0) / 100000, 1.0),
                reason=f"Congress: {trade['representative']} bought {trade['amount_range']}",
                metadata={
                    'company_name': trade.get('asset_description', '')[:50],
                    'owner_name': trade.get('representative', ''),
                    'title': 'U.S. House',
                    'trade_date': trade.get('transaction_date', ''),
                    'score': 0,
                    'value': trade.get('min_value', 0),
                    'cluster_size': 0,
                },
            ))

        return signals


register_strategy(CongressTradingStrategy())
