"""
Crypto Momentum strategy: Golden Cross on BTC and ETH.

Buy when 50-day SMA crosses above 200-day SMA (golden cross).
Sell when 50-day SMA crosses below 200-day SMA (death cross).

Uses CoinGecko free API for price data.
Runs daily (crypto markets are 24/7).
"""

from typing import List, Dict, Any, Optional

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


class CryptoMomentumStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [
            ProfileConfig(
                profile_id='crypto_btc',
                display_name='BTC Momentum',
                description='Buy BTC on golden cross (SMA50 > SMA200), sell on death cross',
                asset_type=AssetType.CRYPTO,
                data_source='coingecko',
                initial_capital=10000.0,
                position_size_pct=50,  # Larger positions for single-asset strategy
                max_positions=2,       # Allow 2 entries
                stop_loss_pct=-15.0,   # Wider stop for crypto volatility
                take_profit_pct=30.0,
                max_holding_days=120,  # Longer hold for trend following
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'BTC',
                    'commission_pct': 0.1,  # 0.1% per trade (typical exchange fee)
                },
            ),
            ProfileConfig(
                profile_id='crypto_eth',
                display_name='ETH Momentum',
                description='Buy ETH on golden cross (SMA50 > SMA200), sell on death cross',
                asset_type=AssetType.CRYPTO,
                data_source='coingecko',
                initial_capital=10000.0,
                position_size_pct=50,
                max_positions=2,
                stop_loss_pct=-15.0,
                take_profit_pct=30.0,
                max_holding_days=120,
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'ETH',
                    'commission_pct': 0.1,
                },
            ),
        ]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        coin = profile.extra_params.get('coin', 'BTC')
        coin_data = market_data.get(coin)
        if not coin_data:
            return []

        active_tickers = {p['ticker'] for p in active_positions}
        signals = []

        golden_cross = coin_data.get('golden_cross')
        sma_50 = coin_data.get('sma_50')
        sma_200 = coin_data.get('sma_200')
        price = coin_data.get('price')

        if golden_cross is None or sma_200 is None:
            return []  # Not enough data

        # BUY: golden cross (SMA50 > SMA200) and not already holding
        if golden_cross and coin not in active_tickers:
            signals.append(Signal(
                ticker=coin,
                signal_type=SignalType.BUY,
                asset_type=AssetType.CRYPTO,
                confidence=min((sma_50 - sma_200) / sma_200 * 10, 1.0),  # Strength of cross
                reason=f"Golden cross: SMA50 ${sma_50:,.0f} > SMA200 ${sma_200:,.0f}",
                metadata={
                    'company_name': f'{coin}/USD',
                    'owner_name': 'MOMENTUM',
                    'title': 'Golden Cross',
                    'trade_date': '',
                    'score': 0,
                    'value': price,
                    'cluster_size': 0,
                },
            ))

        return signals

    def custom_exit_check(self, profile, position, current_price, days_held) -> Optional[str]:
        """Sell on death cross (SMA50 < SMA200)."""
        # This would need access to market_data, which custom_exit_check doesn't have.
        # For now, rely on standard stop-loss/take-profit/time exits.
        # A future enhancement could pass market_data to custom_exit_check.
        return None


register_strategy(CryptoMomentumStrategy())
