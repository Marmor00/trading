"""
OpenInsider CEO/CFO strategy: Buy when a CEO or CFO purchases >$50k.
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class OpenInsiderCEOStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [ProfileConfig(
            profile_id='ceo_any',
            display_name='CEO/CFO',
            description='Buy when CEO or CFO purchases >$50k of their company stock',
            asset_type=AssetType.STOCK,
            data_source='openinsider',
            position_size_pct=10,
            max_positions=10,
            extra_params={'min_value': 50000},
        )]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        min_value = profile.extra_params.get('min_value', 50000)
        active_tickers = {p['ticker'] for p in active_positions}
        signals = []

        for trade in market_data:
            title = str(trade.get('Title', '')).upper()
            if 'CEO' not in title and 'CFO' not in title:
                continue
            value = trade.get('value_numeric', 0)
            if value < min_value:
                continue
            if trade['ticker'] in active_tickers:
                continue

            signals.append(Signal(
                ticker=trade['ticker'],
                signal_type=SignalType.BUY,
                asset_type=AssetType.STOCK,
                confidence=0.8,
                reason=f"CEO/CFO purchase ${value:,.0f}",
                metadata={
                    'company_name': trade.get('company_name', ''),
                    'owner_name': trade.get('owner_name', ''),
                    'title': trade.get('Title', ''),
                    'trade_date': trade.get('trade_date', ''),
                    'score': trade.get('score', 0),
                    'value': value,
                    'cluster_size': trade.get('cluster_size', 0),
                },
            ))

        return signals


register_strategy(OpenInsiderCEOStrategy())
