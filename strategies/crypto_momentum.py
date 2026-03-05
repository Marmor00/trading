"""
Crypto Momentum strategy: Multi-signal approach for BTC, ETH, SOL, ADA, DOGE.

Primary signal: Golden Cross (SMA50 > SMA200) - rare but strong.
Secondary signals (for more frequent trading):
  - Short-term momentum: SMA10 > SMA30 (faster moving averages)
  - RSI oversold bounce: RSI < 35 (oversold, potential reversal)
  - Price above SMA20: Simple trend-following

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
                description='Buy BTC on momentum signals (golden cross, short-term trend, RSI oversold)',
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
                description='Buy ETH on momentum signals (golden cross, short-term trend, RSI oversold)',
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
                description='Buy SOL on momentum signals + RSI filter (skip if overbought)',
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
                description='Buy ADA on momentum signals + RSI filter (skip if overbought)',
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
                description='Buy DOGE on momentum signals + RSI filter (skip if overbought)',
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

        # Already holding this coin
        if coin in active_tickers:
            return []

        signals = []
        price = coin_data.get('price')
        sma_10 = coin_data.get('sma_10')
        sma_20 = coin_data.get('sma_20')
        sma_30 = coin_data.get('sma_30')
        sma_50 = coin_data.get('sma_50')
        sma_200 = coin_data.get('sma_200')
        rsi_val = coin_data.get('rsi_14')
        golden_cross = coin_data.get('golden_cross')
        short_term_bullish = coin_data.get('short_term_bullish')

        if price is None:
            return []

        # RSI filter: skip if overbought (only for profiles with use_rsi_filter=True)
        use_rsi = profile.extra_params.get('use_rsi_filter', False)
        if use_rsi and rsi_val is not None and rsi_val > 70:
            return []  # Overbought, skip all signals

        rsi_info = f", RSI {rsi_val:.0f}" if rsi_val else ""

        # Signal 1: Golden Cross (strongest signal, rare)
        if golden_cross and sma_50 and sma_200:
            signals.append(Signal(
                ticker=coin,
                signal_type=SignalType.BUY,
                asset_type=AssetType.CRYPTO,
                confidence=0.9,
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
                        "Golden cross: 50-day average crossed above 200-day average. "
                        "Classic bullish signal indicating strong upward momentum."
                    ),
                },
            ))
            return signals  # Golden cross takes priority

        # Signal 2: Short-term momentum (SMA10 > SMA30)
        if short_term_bullish and sma_10 and sma_30:
            signals.append(Signal(
                ticker=coin,
                signal_type=SignalType.BUY,
                asset_type=AssetType.CRYPTO,
                confidence=0.7,
                reason=f"Short-term bullish: SMA10 ${sma_10:,.2f} > SMA30 ${sma_30:,.2f}{rsi_info}",
                metadata={
                    'company_name': f'{coin}/USD',
                    'owner_name': 'MOMENTUM',
                    'title': 'Short-Term Momentum',
                    'trade_date': '',
                    'score': 0,
                    'value': price,
                    'cluster_size': 0,
                    'explanation': (
                        "Short-term momentum: 10-day average above 30-day average. "
                        "Indicates recent price strength and potential continuation."
                    ),
                },
            ))
            return signals

        # Signal 3: RSI oversold bounce (RSI < 35)
        if rsi_val is not None and rsi_val < 35:
            signals.append(Signal(
                ticker=coin,
                signal_type=SignalType.BUY,
                asset_type=AssetType.CRYPTO,
                confidence=0.6,
                reason=f"RSI oversold: {rsi_val:.0f} (below 35 threshold)",
                metadata={
                    'company_name': f'{coin}/USD',
                    'owner_name': 'MOMENTUM',
                    'title': 'Oversold Bounce',
                    'trade_date': '',
                    'score': 0,
                    'value': price,
                    'cluster_size': 0,
                    'explanation': (
                        f"RSI at {rsi_val:.0f} indicates oversold conditions. "
                        "Price may be due for a bounce or reversal."
                    ),
                },
            ))
            return signals

        # Signal 4: Price above SMA20 (basic trend following)
        if sma_20 and price > sma_20:
            pct_above = ((price - sma_20) / sma_20) * 100
            # Only trigger if recently crossed (within 2% above)
            if 0 < pct_above < 2:
                signals.append(Signal(
                    ticker=coin,
                    signal_type=SignalType.BUY,
                    asset_type=AssetType.CRYPTO,
                    confidence=0.5,
                    reason=f"Price ${price:,.2f} crossed above SMA20 ${sma_20:,.2f} (+{pct_above:.1f}%){rsi_info}",
                    metadata={
                        'company_name': f'{coin}/USD',
                        'owner_name': 'MOMENTUM',
                        'title': 'Trend Following',
                        'trade_date': '',
                        'score': 0,
                        'value': price,
                        'cluster_size': 0,
                        'explanation': (
                            "Price just crossed above 20-day moving average. "
                            "Simple trend-following signal suggesting upward momentum."
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
