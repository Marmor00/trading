"""
Strategy registry: auto-discovers and loads all strategy modules.
"""

import importlib
import pkgutil
from typing import List, Dict, Tuple

from engine.models import ProfileConfig
from strategies.base_strategy import BaseStrategy


# Global registry
_strategies: Dict[str, Tuple[BaseStrategy, ProfileConfig]] = {}


def _discover_strategies():
    """Import all modules in strategies/ package to trigger registration."""
    import strategies
    for importer, modname, ispkg in pkgutil.iter_modules(strategies.__path__):
        if modname in ('base_strategy', 'registry', '__init__'):
            continue
        try:
            importlib.import_module(f"strategies.{modname}")
        except Exception as e:
            print(f"Warning: Could not load strategy module '{modname}': {e}")


def register_strategy(strategy: BaseStrategy):
    """Register a strategy instance and all its profiles."""
    for profile in strategy.get_profiles():
        _strategies[profile.profile_id] = (strategy, profile)


def get_all_profiles(schedule_filter=None) -> List[Tuple[BaseStrategy, ProfileConfig]]:
    """Get all registered (strategy, profile) pairs.

    Args:
        schedule_filter: If set, only return profiles matching this schedule
                        ('weekdays', 'daily', or None for all)
    """
    if not _strategies:
        _discover_strategies()

    results = list(_strategies.values())
    if schedule_filter and schedule_filter != 'all':
        results = [(s, p) for s, p in results if p.schedule == schedule_filter]
    return results


def get_profile(profile_id) -> Tuple[BaseStrategy, ProfileConfig]:
    """Get a specific (strategy, profile) pair by profile_id."""
    if not _strategies:
        _discover_strategies()
    return _strategies.get(profile_id)


def get_data_sources_needed(schedule_filter=None) -> set:
    """Get the set of data sources needed by active profiles."""
    pairs = get_all_profiles(schedule_filter)
    return {p.data_source for _, p in pairs if p.data_source != 'none'}
