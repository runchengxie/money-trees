from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FactorFamily:
    family_id: str
    display_name: str
    source: str
    local_generation: str
    required_inputs: tuple[str, ...]
    notes: str


FACTOR_FAMILIES: dict[str, FactorFamily] = {
    "alpha101": FactorFamily(
        family_id="alpha101",
        display_name="WorldQuant 101 Formulaic Alphas",
        source="Kakushadze, 101 Formulaic Alphas; DolphinDB wq101alpha; third-party Python ports.",
        local_generation="external",
        required_inputs=("open", "high", "low", "close", "volume", "vwap", "cap", "indclass"),
        notes=(
            "Money Tree expects generated alpha columns to be merged into the daily panel. "
            "Industry-aware factors need point-in-time industry and market-cap inputs."
        ),
    ),
    "alpha191": FactorFamily(
        family_id="alpha191",
        display_name="GTJA 191 Alpha",
        source="GTJA 2017 short-horizon price-volume factor report; DolphinDB gtja191Alpha.",
        local_generation="external",
        required_inputs=("open", "high", "low", "close", "volume", "vwap", "index_open", "index_close"),
        notes=(
            "Money Tree expects generated alpha columns to be merged into the daily panel. "
            "Some formulas use benchmark index open/close series."
        ),
    ),
    "alpha158": FactorFamily(
        family_id="alpha158",
        display_name="Qlib Alpha158",
        source="Microsoft Qlib Alpha158 data handler.",
        local_generation="moneytree.factors.qlib.build_alpha158_features",
        required_inputs=("open", "high", "low", "close", "volume", "vwap"),
        notes=(
            "The built-in generator is a Qlib-style 158-column daily OHLCV baseline. "
            "Generate in Qlib and merge if byte-for-byte Qlib parity is required."
        ),
    ),
    "alpha360": FactorFamily(
        family_id="alpha360",
        display_name="Qlib Alpha360",
        source="Microsoft Qlib Alpha360 data handler.",
        local_generation="moneytree.factors.qlib.build_alpha360_features",
        required_inputs=("open", "high", "low", "close", "volume", "vwap"),
        notes="The built-in generator creates 6 daily OHLCV/VWAP fields over 60 lags.",
    ),
}


def list_factor_families() -> list[str]:
    return sorted(FACTOR_FAMILIES)


def get_factor_family(family_id: str) -> FactorFamily:
    key = family_id.strip().lower().replace("-", "_")
    try:
        return FACTOR_FAMILIES[key]
    except KeyError as exc:
        available = ", ".join(list_factor_families())
        raise KeyError(f"Unknown factor family '{family_id}'. Available: {available}.") from exc
