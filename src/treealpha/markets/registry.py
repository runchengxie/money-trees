from __future__ import annotations

from treealpha.markets.base import BaseMarketProfile
from treealpha.markets.us import USMarketProfile


_MARKET_REGISTRY: dict[str, BaseMarketProfile] = {
    "us": USMarketProfile(),
}


def register_market_profile(profile: BaseMarketProfile) -> None:
    _MARKET_REGISTRY[profile.market_id] = profile


def get_market_profile(market_id: str) -> BaseMarketProfile:
    try:
        return _MARKET_REGISTRY[market_id]
    except KeyError as exc:
        available = ", ".join(sorted(_MARKET_REGISTRY))
        raise KeyError(f"Unknown market profile '{market_id}'. Available: {available}.") from exc


def list_market_profiles() -> list[str]:
    return sorted(_MARKET_REGISTRY)
