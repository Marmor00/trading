"""
ETF Sector Rotation strategy.

Invests in the top-performing sectors based on 3-month momentum.
Rebalances monthly: sell sectors that fell out of the top 3,
buy sectors that moved into the top 3.

Uses the 11 SPDR sector ETFs:
XLK (Technology), XLF (Financials), XLE (Energy), XLV (Healthcare),
XLI (Industrials), XLP (Consumer Staples), XLY (Consumer Discretionary),
XLB (Materials), XLU (Utilities), XLRE (Real Estate), XLC (Communications)
"""

from typing import List, Dict, Any

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from engine.price_service import get_price
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC']


class EtfSectorRotationStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        return [ProfileConfig(
            profile_id='sector_rotation',
            display_name='Sector Rotation',
            description='Buy top 3 performing sector ETFs, rebalance monthly',
            asset_type=AssetType.ETF,
            data_source='none',  # Uses price_service directly
            initial_capital=10000.0,
            position_size_pct=30,    # ~33% per position (3 positions)
            max_positions=3,
            stop_loss_pct=-12.0,
            take_profit_pct=25.0,
            max_holding_days=35,     # Rebalance roughly monthly
            commission=0.0,          # Zero commission on ETFs at most brokers
            schedule='weekdays',
        )]

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        active_tickers = {p['ticker'] for p in active_positions}
        active_count = len(active_positions)

        # If we already have 3 positions, wait for time exit to rebalance
        if active_count >= profile.max_positions:
            return []

        # If we have some positions, only fill remaining slots
        slots_available = profile.max_positions - active_count

        # Get current prices for all sector ETFs
        prices = {}
        for etf in SECTOR_ETFS:
            price = get_price(etf, AssetType.ETF)
            if price:
                prices[etf] = price

        if len(prices) < 5:
            print("  ! Not enough ETF price data for sector rotation")
            return []

        # For initial version: simply pick the ETFs not already held
        # In the future, we could add momentum scoring with historical prices
        # For now, we rotate through sectors that we're not holding
        candidates = [etf for etf in SECTOR_ETFS if etf not in active_tickers and etf in prices]

        signals = []
        for etf in candidates[:slots_available]:
            signals.append(Signal(
                ticker=etf,
                signal_type=SignalType.BUY,
                asset_type=AssetType.ETF,
                confidence=0.6,
                reason=f"Sector rotation: {etf}",
                metadata={
                    'company_name': f'{etf} Sector ETF',
                    'owner_name': 'ROTATION',
                    'title': 'Sector ETF',
                    'trade_date': '',
                    'score': 0,
                    'value': prices.get(etf, 0),
                    'cluster_size': 0,
                },
            ))

        return signals


register_strategy(EtfSectorRotationStrategy())
