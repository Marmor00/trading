"""
OpenInsider Cluster strategy: Buy when 2+ insiders are buying the same stock.
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class OpenInsiderClusterStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [ProfileConfig(
            profile_id='cluster_2',
            display_name='Cluster 2+',
            description='Buy when 2+ insiders are buying the same stock simultaneously',
            asset_type=AssetType.STOCK,
            data_source='openinsider',
            position_size_pct=10,
            max_positions=10,
            extra_params={'min_cluster': 2},
        )]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        min_cluster = profile.extra_params.get('min_cluster', 2)
        active_tickers = {p['ticker'] for p in active_positions}
        seen_tickers = set()
        signals = []

        for trade in market_data:
            cluster_size = trade.get('cluster_size', 1)
            if cluster_size < min_cluster:
                continue
            ticker = trade['ticker']
            if ticker in active_tickers or ticker in seen_tickers:
                continue

            seen_tickers.add(ticker)
            signals.append(Signal(
                ticker=ticker,
                signal_type=SignalType.BUY,
                asset_type=AssetType.STOCK,
                confidence=min(cluster_size / 5.0, 1.0),
                reason=f"Cluster of {cluster_size} insiders buying",
                metadata={
                    'company_name': trade.get('company_name', ''),
                    'owner_name': trade.get('owner_name', ''),
                    'title': trade.get('Title', ''),
                    'trade_date': trade.get('trade_date', ''),
                    'score': trade.get('score', 0),
                    'value': trade.get('value_numeric', 0),
                    'cluster_size': cluster_size,
                },
            ))

        return signals


register_strategy(OpenInsiderClusterStrategy())
