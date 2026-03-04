"""
Abstract base class for all trading strategies.

To create a new strategy:
1. Create a new file in strategies/
2. Subclass BaseStrategy
3. Implement get_profiles() and generate_signals()
4. The registry will auto-discover it
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

from engine.models import ProfileConfig, Signal


class BaseStrategy(ABC):

    @abstractmethod
    def get_profiles(self) -> List[ProfileConfig]:
        """Return the profiles this strategy provides.

        A single strategy module can register multiple profiles.
        Example: OpenInsiderScoreStrategy returns 3 profiles (score_60, score_70, score_80).
        """
        pass

    @abstractmethod
    def generate_signals(
        self,
        profile: ProfileConfig,
        market_data: Any,
        active_positions: List[Dict],
        portfolio_state: Dict,
    ) -> List[Signal]:
        """Generate buy/sell signals given market data and current state.

        The strategy should NOT execute trades -- only return signals.
        The engine decides whether to execute based on cash, position limits, etc.

        Args:
            profile: The specific profile configuration
            market_data: Raw data from the data source (strategy-specific)
            active_positions: Currently held positions for this profile
            portfolio_state: {cash, invested_value, total, return_pct, ...}

        Returns:
            List of Signal objects
        """
        pass

    def custom_exit_check(
        self,
        profile: ProfileConfig,
        position: Dict,
        current_price: float,
        days_held: int,
    ) -> Optional[str]:
        """Optional: custom exit logic beyond standard stop-loss/take-profit/time.

        Return an exit reason string to trigger a sell, or None to hold.
        """
        return None
