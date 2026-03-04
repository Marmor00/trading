"""
OpenInsider Score-based strategies: Score >=60, >=70, >=80.

One module, three profiles with different score thresholds.
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class OpenInsiderScoreStrategy(BaseStrategy):

    THRESHOLDS = {
        'score_60': {'name': 'Score >=60', 'threshold': 60, 'position_pct': 8, 'max_pos': 12},
        'score_70': {'name': 'Score >=70', 'threshold': 70, 'position_pct': 10, 'max_pos': 10},
        'score_80': {'name': 'Score >=80', 'threshold': 80, 'position_pct': 12, 'max_pos': 8},
    }

    def get_profiles(self) -> List[ProfileConfig]:
        profiles = []
        for pid, cfg in self.THRESHOLDS.items():
            profiles.append(ProfileConfig(
                profile_id=pid,
                display_name=cfg['name'],
                description=f"Buy when insider score >= {cfg['threshold']}",
                asset_type=AssetType.STOCK,
                data_source='openinsider',
                position_size_pct=cfg['position_pct'],
                max_positions=cfg['max_pos'],
                extra_params={'score_threshold': cfg['threshold']},
            ))
        return profiles

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        threshold = profile.extra_params.get('score_threshold', 60)
        active_tickers = {p['ticker'] for p in active_positions}
        signals = []

        for trade in market_data:
            score = trade.get('score', 0)
            if score < threshold:
                continue
            if trade['ticker'] in active_tickers:
                continue

            signals.append(Signal(
                ticker=trade['ticker'],
                signal_type=SignalType.BUY,
                asset_type=AssetType.STOCK,
                confidence=min(score / 100.0, 1.0),
                reason=f"Insider score {score} >= {threshold}",
                metadata={
                    'company_name': trade.get('company_name', ''),
                    'owner_name': trade.get('owner_name', ''),
                    'title': trade.get('Title', ''),
                    'trade_date': trade.get('trade_date', ''),
                    'score': score,
                    'value': trade.get('value_numeric', 0),
                    'cluster_size': trade.get('cluster_size', 0),
                },
            ))

        return signals


# Auto-register on import
register_strategy(OpenInsiderScoreStrategy())
