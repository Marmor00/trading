"""
Technical Scanner strategy: config-driven profiles using technical indicators.

One module generates 10 profiles, all sharing market scanner data.
Each profile defines which indicator to use, which ticker universe to scan,
buy/sell thresholds, and position sizing parameters.

Adding a new profile = adding a dict to SCANNER_PROFILES. No new class needed.
"""

from typing import List, Optional

from engine.models import ProfileConfig, Signal, SignalType, AssetType
from strategies.base_strategy import BaseStrategy
from strategies.registry import register_strategy


# ============================================================
# EDUCATIONAL EXPLANATIONS (shown in dashboard and Telegram)
# ============================================================

INDICATOR_EXPLANATIONS = {
    'rsi': (
        "RSI (Relative Strength Index) measures if a stock is oversold or overbought. "
        "Below 30 means the price dropped fast and may bounce back. "
        "Above 70 means it rose fast and may pull back."
    ),
    'macd': (
        "MACD tracks momentum using two moving averages. "
        "A bullish crossover (MACD line crosses above signal line) suggests "
        "the trend is turning upward. A bearish crossover suggests the opposite."
    ),
    'bollinger': (
        "Bollinger Bands show how volatile a stock is. "
        "When price touches the lower band, it may be oversold and due for a bounce. "
        "When it touches the upper band, it may be overbought."
    ),
    'sma_cross': (
        "Golden Cross: the 50-day average crosses above the 200-day average. "
        "This is a classic long-term bullish signal used by institutional investors. "
        "Death Cross is the opposite and signals potential downtrend."
    ),
    'week52': (
        "52-Week Position shows where the price sits relative to its annual range. "
        "Near the low = deep value territory (stock is beaten down). "
        "Near the high = momentum territory (stock is strong)."
    ),
    'combo_rsi_bb': (
        "Double confirmation: both RSI (oversold) AND Bollinger Bands (near lower band) "
        "agree the stock is undervalued. This is more selective but higher conviction "
        "than using either indicator alone."
    ),
}


# ============================================================
# PROFILE CONFIGURATIONS
# ============================================================

SCANNER_PROFILES = [
    # --- RSI PROFILES ---
    {
        'id': 'rsi_oversold_mega',
        'display_name': 'RSI Oversold (Mega)',
        'description': 'Buy mega-cap stocks when RSI drops below 35 (oversold)',
        'indicator': 'rsi',
        'universe': 'mega_cap',
        'buy_condition': 'rsi_below',
        'buy_threshold': 35,
        'sell_condition': 'rsi_above',
        'sell_threshold': 70,
        'position_size_pct': 10,
        'max_positions': 8,
        'stop_loss_pct': -8.0,
        'take_profit_pct': 15.0,
        'max_holding_days': 30,
    },
    {
        'id': 'rsi_oversold_growth',
        'display_name': 'RSI Oversold (Growth)',
        'description': 'Buy growth stocks when RSI drops below 30 (oversold)',
        'indicator': 'rsi',
        'universe': 'tech_growth',
        'buy_condition': 'rsi_below',
        'buy_threshold': 30,
        'sell_condition': 'rsi_above',
        'sell_threshold': 75,
        'position_size_pct': 8,
        'max_positions': 6,
        'stop_loss_pct': -10.0,
        'take_profit_pct': 20.0,
        'max_holding_days': 25,
    },

    # --- MACD PROFILES ---
    {
        'id': 'macd_cross_mega',
        'display_name': 'MACD Cross (Mega)',
        'description': 'Buy mega-cap stocks on bullish MACD crossover',
        'indicator': 'macd',
        'universe': 'mega_cap',
        'buy_condition': 'macd_crossover_up',
        'sell_condition': 'macd_crossover_down',
        'position_size_pct': 10,
        'max_positions': 8,
        'stop_loss_pct': -7.0,
        'take_profit_pct': 12.0,
        'max_holding_days': 40,
    },
    {
        'id': 'macd_cross_growth',
        'display_name': 'MACD Cross (Growth)',
        'description': 'Buy growth stocks on bullish MACD crossover',
        'indicator': 'macd',
        'universe': 'tech_growth',
        'buy_condition': 'macd_crossover_up',
        'sell_condition': 'macd_crossover_down',
        'position_size_pct': 8,
        'max_positions': 6,
        'stop_loss_pct': -10.0,
        'take_profit_pct': 18.0,
        'max_holding_days': 35,
    },
    {
        'id': 'macd_cross_etf',
        'display_name': 'MACD Cross (ETFs)',
        'description': 'Buy ETFs on bullish MACD crossover',
        'indicator': 'macd',
        'universe': 'etf_universe',
        'buy_condition': 'macd_crossover_up',
        'sell_condition': 'macd_crossover_down',
        'position_size_pct': 15,
        'max_positions': 4,
        'stop_loss_pct': -5.0,
        'take_profit_pct': 10.0,
        'max_holding_days': 30,
    },

    # --- BOLLINGER BAND PROFILES ---
    {
        'id': 'bband_bounce_mega',
        'display_name': 'BB Bounce (Mega)',
        'description': 'Buy mega-cap stocks near lower Bollinger Band (mean reversion)',
        'indicator': 'bollinger',
        'universe': 'mega_cap',
        'buy_condition': 'bb_below',
        'buy_threshold': 0.20,   # pct_b < 20% = near lower band
        'sell_condition': 'bb_above',
        'sell_threshold': 0.95,  # pct_b > 95% = near upper band
        'position_size_pct': 10,
        'max_positions': 8,
        'stop_loss_pct': -6.0,
        'take_profit_pct': 10.0,
        'max_holding_days': 20,
    },
    {
        'id': 'bband_bounce_etf',
        'display_name': 'BB Bounce (ETFs)',
        'description': 'Buy ETFs near lower Bollinger Band',
        'indicator': 'bollinger',
        'universe': 'etf_universe',
        'buy_condition': 'bb_below',
        'buy_threshold': 0.20,
        'sell_condition': 'bb_above',
        'sell_threshold': 0.95,
        'position_size_pct': 15,
        'max_positions': 4,
        'stop_loss_pct': -5.0,
        'take_profit_pct': 8.0,
        'max_holding_days': 15,
    },

    # --- SMA CROSSOVER PROFILE ---
    {
        'id': 'golden_cross_mega',
        'display_name': 'Golden Cross (Mega)',
        'description': 'Buy mega-cap stocks on SMA50/200 golden cross',
        'indicator': 'sma_cross',
        'universe': 'mega_cap',
        'buy_condition': 'golden_cross',
        'sell_condition': 'death_cross',
        'position_size_pct': 12,
        'max_positions': 6,
        'stop_loss_pct': -10.0,
        'take_profit_pct': 20.0,
        'max_holding_days': 60,
    },

    # --- 52-WEEK PROFILE ---
    {
        'id': 'w52_low_mega',
        'display_name': '52W Low Buy (Mega)',
        'description': 'Buy mega-cap stocks within 25% of 52-week low (deep value)',
        'indicator': 'week52',
        'universe': 'mega_cap',
        'buy_condition': 'near_52w_low',
        'buy_threshold': 25,  # position <= 25% of annual range
        'sell_condition': 'near_52w_high',
        'sell_threshold': 85,
        'position_size_pct': 10,
        'max_positions': 6,
        'stop_loss_pct': -12.0,
        'take_profit_pct': 25.0,
        'max_holding_days': 45,
    },

    # --- COMBO PROFILE (RSI + Bollinger confirmation) ---
    {
        'id': 'rsi_bb_combo_mega',
        'display_name': 'RSI+BB Combo (Mega)',
        'description': 'Buy when BOTH RSI<35 AND price near lower Bollinger Band',
        'indicator': 'combo_rsi_bb',
        'universe': 'mega_cap',
        'buy_condition': 'rsi_below_and_bb_below',
        'rsi_threshold': 35,
        'bb_threshold': 0.15,
        'sell_condition': 'rsi_above',
        'sell_threshold': 65,
        'position_size_pct': 12,
        'max_positions': 6,
        'stop_loss_pct': -7.0,
        'take_profit_pct': 12.0,
        'max_holding_days': 25,
    },
]


# ============================================================
# STRATEGY CLASS
# ============================================================

class TechnicalScannerStrategy(BaseStrategy):

    def get_profiles(self) -> List[ProfileConfig]:
        profiles = []
        for cfg in SCANNER_PROFILES:
            asset_type = AssetType.ETF if cfg['universe'] == 'etf_universe' else AssetType.STOCK
            profiles.append(ProfileConfig(
                profile_id=cfg['id'],
                display_name=cfg['display_name'],
                description=cfg['description'],
                asset_type=asset_type,
                data_source='market_scanner',
                position_size_pct=cfg['position_size_pct'],
                max_positions=cfg['max_positions'],
                stop_loss_pct=cfg['stop_loss_pct'],
                take_profit_pct=cfg['take_profit_pct'],
                max_holding_days=cfg['max_holding_days'],
                commission=0.0,  # Most brokers: zero commission on stocks/ETFs
                schedule='weekdays',
                extra_params=cfg,
            ))
        return profiles

    def generate_signals(self, profile, market_data, active_positions, portfolio_state) -> List[Signal]:
        if not market_data:
            return []

        cfg = profile.extra_params
        target_universe = cfg.get('universe', 'mega_cap')
        indicator = cfg.get('indicator', 'rsi')
        buy_condition = cfg.get('buy_condition', '')

        active_tickers = {p['ticker'] for p in active_positions}
        signals = []

        for ticker, data in market_data.items():
            if data.get('universe') != target_universe:
                continue
            if ticker in active_tickers:
                continue

            buy_signal = self._check_buy(indicator, buy_condition, data, cfg)
            if buy_signal:
                confidence, reason = buy_signal
                explanation = INDICATOR_EXPLANATIONS.get(indicator, '')

                signals.append(Signal(
                    ticker=ticker,
                    signal_type=SignalType.BUY,
                    asset_type=profile.asset_type,
                    confidence=confidence,
                    reason=reason,
                    metadata={
                        'company_name': ticker,
                        'owner_name': 'SCANNER',
                        'title': cfg['display_name'],
                        'trade_date': '',
                        'score': 0,
                        'value': data.get('price', 0),
                        'cluster_size': 0,
                        'explanation': explanation,
                    },
                ))

        return signals

    def _check_buy(self, indicator, buy_condition, data, cfg):
        """Check if buy condition is met. Returns (confidence, reason) or None."""

        if indicator == 'rsi':
            rsi_val = data.get('rsi_14')
            if rsi_val is None:
                return None
            threshold = cfg.get('buy_threshold', 30)
            if buy_condition == 'rsi_below' and rsi_val < threshold:
                confidence = max(0.5, 1.0 - (rsi_val / threshold))
                return (confidence, f"RSI {rsi_val:.1f} < {threshold} (oversold)")
            return None

        elif indicator == 'macd':
            macd_data = data.get('macd')
            if not macd_data:
                return None
            if buy_condition == 'macd_crossover_up' and macd_data.get('recent_crossover_up'):
                hist = macd_data.get('histogram', 0)
                confidence = min(0.5 + abs(hist) * 10, 1.0)
                fresh = " (today)" if macd_data.get('crossover_up') else " (recent)"
                return (confidence, f"MACD bullish crossover{fresh} (histogram={hist:.4f})")
            return None

        elif indicator == 'bollinger':
            bb = data.get('bollinger')
            if not bb:
                return None
            threshold = cfg.get('buy_threshold', 0.05)
            if buy_condition == 'bb_below' and bb['pct_b'] < threshold:
                confidence = max(0.5, 1.0 - bb['pct_b'])
                return (confidence, f"Below lower Bollinger Band (pct_b={bb['pct_b']:.2f})")
            return None

        elif indicator == 'sma_cross':
            cross = data.get('sma_cross_50_200')
            if not cross:
                return None
            if buy_condition == 'golden_cross' and cross.get('recent_golden_cross'):
                fresh = " (today)" if cross.get('golden_cross') else " (recent)"
                return (0.8, f"Golden cross{fresh}: SMA50 ${cross['fast_sma']:.0f} > SMA200 ${cross['slow_sma']:.0f}")
            return None

        elif indicator == 'week52':
            w52 = data.get('week52')
            if not w52:
                return None
            threshold = cfg.get('buy_threshold', 15)
            if buy_condition == 'near_52w_low' and w52['position'] <= threshold:
                confidence = max(0.5, 1.0 - (w52['position'] / 100))
                return (confidence, f"Near 52W low ({w52['pct_from_low']:+.1f}% from low, position {w52['position']:.0f}%)")
            return None

        elif indicator == 'combo_rsi_bb':
            rsi_val = data.get('rsi_14')
            bb = data.get('bollinger')
            if rsi_val is None or not bb:
                return None
            rsi_thresh = cfg.get('rsi_threshold', 35)
            bb_thresh = cfg.get('bb_threshold', 0.15)
            if rsi_val < rsi_thresh and bb['pct_b'] < bb_thresh:
                confidence = min(0.6 + (1.0 - rsi_val / 100) * 0.4, 1.0)
                return (confidence, f"RSI {rsi_val:.1f} + BB {bb['pct_b']:.2f} (double confirmation)")
            return None

        return None

    def custom_exit_check(self, profile, position, current_price, days_held) -> Optional[str]:
        """Custom exit. Note: currently relies on stop-loss/take-profit/time exits.
        Future: pass market_data to enable indicator-based exits."""
        return None


register_strategy(TechnicalScannerStrategy())
