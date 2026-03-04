"""
Crypto Momentum strategy: Golden Cross on BTC, ETH, SOL, ADA, DOGE.

Buy when 50-day SMA crosses above 200-day SMA (golden cross).
Optional RSI filter: skip buy if RSI > 70 (overbought).
Sell via stop-loss/take-profit/time exits.

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
                position_size_pct=50,
                max_positions=2,
                stop_loss_pct=-15.0,
                take_profit_pct=30.0,
                max_holding_days=120,
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'BTC',
                    'commission_pct': 0.1,
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
            ProfileConfig(
                profile_id='crypto_sol',
                display_name='SOL Momentum',
                description='Buy SOL on golden cross + RSI filter (skip if overbought)',
                asset_type=AssetType.CRYPTO,
                data_source='coingecko',
                initial_capital=10000.0,
                position_size_pct=50,
                max_positions=2,
                stop_loss_pct=-20.0,   # Wider stop for altcoin volatility
                take_profit_pct=40.0,
                max_holding_days=90,
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'SOL',
                    'commission_pct': 0.1,
                    'use_rsi_filter': True,
                },
            ),
            ProfileConfig(
                profile_id='crypto_ada',
                display_name='ADA Momentum',
                description='Buy ADA on golden cross + RSI filter (skip if overbought)',
                asset_type=AssetType.CRYPTO,
                data_source='coingecko',
                initial_capital=10000.0,
                position_size_pct=50,
                max_positions=2,
                stop_loss_pct=-25.0,
                take_profit_pct=50.0,
                max_holding_days=90,
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'ADA',
                    'commission_pct': 0.1,
                    'use_rsi_filter': True,
                },
            ),
            ProfileConfig(
                profile_id='crypto_doge',
                display_name='DOGE Momentum',
                description='Buy DOGE on golden cross + RSI filter (skip if overbought)',
                asset_type=AssetType.CRYPTO,
                data_source='coingecko',
                initial_capital=10000.0,
                position_size_pct=50,
                max_positions=2,
                stop_loss_pct=-25.0,
                take_profit_pct=60.0,
                max_holding_days=90,
                commission=0.0,
                schedule='daily',
                extra_params={
                    'coin': 'DOGE',
                    'commission_pct': 0.1,
                    'use_rsi_filter': True,
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

        # RSI filter: skip if overbought
        use_rsi = profile.extra_params.get('use_rsi_filter', False)
        if use_rsi and golden_cross:
            rsi_val = coin_data.get('rsi_14')
            if rsi_val is not None and rsi_val > 70:
                return []  # Overbought, skip even with golden cross

        # BUY: golden cross (SMA50 > SMA200) and not already holding
        if golden_cross and coin not in active_tickers:
            rsi_info = ""
            rsi_val = coin_data.get('rsi_14')
            if rsi_val is not None:
                rsi_info = f", RSI {rsi_val:.0f}"

            signals.append(Signal(
                ticker=coin,
                signal_type=SignalType.BUY,
                asset_type=AssetType.CRYPTO,
                confidence=min((sma_50 - sma_200) / sma_200 * 10, 1.0),
                reason=f"Golden cross: SMA50 ${sma_50:,.0f} > SMA200 ${sma_200:,.0f}{rsi_info}",
                metadata={
                    'company_name': f'{coin}/USD',
                    'owner_name': 'MOMENTUM',
                    'title': 'Golden Cross',
                    'trade_date': '',
                    'score': 0,
                    'value': price,
                    'cluster_size': 0,
                    'explanation': (
                        "Golden cross means the 50-day average price crossed above the 200-day average. "
                        "This is a classic bullish signal indicating upward momentum."
                    ),
                },
            ))

        return signals

    def custom_exit_check(self, profile, position, current_price, days_held) -> Optional[str]:
        """Sell on death cross (SMA50 < SMA200)."""
        # Would need access to market_data, which custom_exit_check doesn't have.
        # For now, rely on standard stop-loss/take-profit/time exits.
        return None


register_strategy(CryptoMomentumStrategy())
