from __future__ import annotations

import sys
from collections.abc import Iterable

import numpy as np
import pandas as pd

from moneytree.data import ensure_date_ticker_index, normalize_factor_dtype
from moneytree.factors.rolling import rolling_rank_last

ALPHA191_COUNT = 191
ALPHA101_COUNT = 101

_TICKER_LEVEL = "ticker"
_DATE_LEVEL = "date"


def _groupby_ticker(series: pd.Series):
    return series.groupby(level=_TICKER_LEVEL, sort=False)


def _groupby_date(series: pd.Series):
    return series.groupby(level=_DATE_LEVEL, sort=False)


class ClassicAlphaContext:
    """Cross-sectional Alpha101/191 computation on a standard (date, ticker) panel.

    The GTJA Alpha191 and WorldQuant Alpha101 formulas are ported from the
    ``wu-alpha191-alpha101`` reference repository, but rank/scale operations are
    evaluated on the cross-section (per trade date) instead of per-ticker
    time-series ranks. All rolling operations are evaluated per ticker.
    """

    def __init__(self, frame: pd.DataFrame, *, use_adjusted_prices: bool = True) -> None:
        panel = ensure_date_ticker_index(frame)
        self._index = panel.index

        def _nan_series() -> pd.Series:
            return pd.Series(np.nan, index=panel.index)

        data: dict[str, pd.Series] = {}

        for field in ("open", "high", "low", "close", "vwap"):
            selected: pd.Series | None = None
            if use_adjusted_prices:
                adjusted_name = f"{field}_adj"
                if adjusted_name in panel.columns:
                    selected = panel[adjusted_name]
            if selected is None and field in panel.columns:
                selected = panel[field]
            data[field] = selected.astype(float) if selected is not None else _nan_series()

        if "volume" in panel.columns:
            data["volume"] = panel["volume"].astype(float).replace(0, 1)
        else:
            data["volume"] = _nan_series()

        close = data["close"]
        data["returns"] = close.groupby(level=_TICKER_LEVEL, sort=False).pct_change()

        if "amount" in panel.columns:
            data["turnover"] = panel["amount"].astype(float)
        else:
            data["turnover"] = _nan_series()

        if "turnover_rate" in panel.columns:
            data["turnover_rate"] = panel["turnover_rate"].astype(float)
        else:
            data["turnover_rate"] = _nan_series()

        if "circ_mv" in panel.columns:
            data["cap"] = panel["circ_mv"].astype(float)
        elif "total_mv" in panel.columns:
            data["cap"] = panel["total_mv"].astype(float)
        else:
            data["cap"] = _nan_series()

        if "industry" in panel.columns:
            data["industry"] = panel["industry"].astype(str)
        else:
            data["industry"] = _nan_series()

        for field, panel_column in (
            ("index_open", "benchmark_open"),
            ("index_close", "benchmark_close"),
        ):
            if panel_column in panel.columns:
                data[field] = panel[panel_column].astype(float)
            else:
                data[field] = _nan_series()

        self._d = data

    # ------------------------------------------------------------------
    # Core operators (cross-sectional rank/scale, per-ticker rolling ops)
    # ------------------------------------------------------------------

    def _ts_sum(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: group.rolling(window).sum())

    def _sma(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: group.rolling(window).mean())

    def _std_dev(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: group.rolling(window).std())

    def _pair_rolling(self, x: pd.Series, y: pd.Series, window: int, method: str) -> pd.Series:
        frame = pd.DataFrame({"a": x, "b": y}, index=x.index)
        parts: list[pd.Series] = []
        for _, group in frame.groupby(level=_TICKER_LEVEL, sort=False):
            if method == "corr":
                parts.append(group["a"].rolling(window).corr(group["b"]))
            else:
                parts.append(group["a"].rolling(window).cov(group["b"]))
        if not parts:
            return pd.Series(np.nan, index=frame.index)
        return pd.concat(parts).reindex(frame.index)

    def _correlation(self, x: pd.Series, y: pd.Series, window: int = 10) -> pd.Series:
        return self._pair_rolling(x, y, window, "corr")

    def _covariance(self, x: pd.Series, y: pd.Series, window: int = 10) -> pd.Series:
        return self._pair_rolling(x, y, window, "cov")

    def _ts_rank(self, df: pd.Series, window: int = 10) -> pd.Series:
        return rolling_rank_last(df, window, min_periods=window)

    def _ts_min(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: group.rolling(window).min())

    def _ts_max(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: group.rolling(window).max())

    def _delta(self, df: pd.Series, period: int = 1) -> pd.Series:
        return _groupby_ticker(df).diff(int(period))

    def _delay(self, df: pd.Series, period: int = 1) -> pd.Series:
        return _groupby_ticker(df).shift(int(period))

    def _rank(self, df: pd.Series) -> pd.Series:
        return _groupby_date(df).rank(pct=True)

    def _scale(self, df: pd.Series, k: int = 1) -> pd.Series:
        def apply_scale(group: pd.Series) -> pd.Series:
            total = group.abs().sum()
            if total == 0 or pd.isna(total):
                return pd.Series(np.nan, index=group.index)
            return k * group / total

        return _groupby_date(df).transform(apply_scale)

    def _ts_argmax(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(
            lambda group: group.rolling(window).apply(np.argmax, raw=True) + 1
        )

    def _ts_argmin(self, df: pd.Series, window: int = 10) -> pd.Series:
        return _groupby_ticker(df).transform(
            lambda group: group.rolling(window).apply(np.argmin, raw=True) + 1
        )

    def _decay_linear(self, df: pd.Series, window: int = 10) -> pd.Series:
        weights = np.arange(1, int(window) + 1, dtype=float)
        weights = weights / weights.sum()

        def apply_decay(values: np.ndarray) -> float:
            return float(np.sum(values * weights))

        return _groupby_ticker(df).transform(
            lambda group: group.rolling(int(window)).apply(apply_decay, raw=True)
        )

    def _ts_cumprod(self, df: pd.Series) -> pd.Series:
        return _groupby_ticker(df).transform(lambda group: (1 + group).cumprod())

    # ------------------------------------------------------------------
    # GTJA Alpha 191 factors
    # ------------------------------------------------------------------

    def alpha_001(self) -> pd.Series:
        p1 = self._rank(self._delta(np.log(self._d["volume"]), 1))
        p2 = self._rank((self._d["close"] - self._d["open"]) / self._d["open"])
        return -1 * self._correlation(p1, p2, 6)

    def alpha_002(self) -> pd.Series:
        denominator = self._d["high"] - self._d["low"]
        denominator = denominator.copy()
        denominator[denominator == 0] = 0.0001
        p1 = (self._d["close"] - self._d["low"]) - (self._d["high"] - self._d["close"])
        p2 = p1 / denominator
        return -1 * self._delta(p2, 1)

    def alpha_003(self) -> pd.Series:
        delay_close = self._delay(self._d["close"], 1)
        cond_greater = self._d["close"] > delay_close

        term = self._d["close"].copy()
        term[cond_greater] = self._d["close"] - pd.concat(
            [self._d["low"], delay_close], axis=1
        ).min(axis=1)
        term[~cond_greater] = self._d["close"] - pd.concat(
            [self._d["high"], delay_close], axis=1
        ).max(axis=1)

        cond_equal = self._d["close"] == delay_close
        term[cond_equal] = 0

        return self._ts_sum(term, 6)

    def alpha_004(self) -> pd.Series:
        adv60 = self._sma(self._d["volume"], 60)
        p1 = self._ts_rank(self._d["close"], 10)
        p2 = self._ts_rank(self._d["volume"] / (adv60 + 1), 4)
        return -1 * self._correlation(p1, p2, 7)

    def alpha_005(self) -> pd.Series:
        return -1 * self._ts_max(
            self._correlation(
                self._ts_rank(self._d["volume"], 5), self._ts_rank(self._d["high"], 5), 5
            ),
            3,
        )

    def alpha_006(self) -> pd.Series:
        return -1 * self._rank(np.sign(self._delta(self._d["open"] * 0.85 + self._d["high"] * 0.15, 4)))

    def alpha_007(self) -> pd.Series:
        p1 = self._rank(self._ts_max(self._d["vwap"] - self._d["close"], 15))
        p2 = self._rank(self._ts_min(self._d["vwap"] - self._d["close"], 15))
        p3 = self._rank(self._delta(self._d["volume"], 3))
        return p1 * p2 * p3

    def alpha_008(self) -> pd.Series:
        return -1 * self._rank(
            self._delta((self._d["high"] + self._d["low"]) / 2 * 0.2 + self._d["vwap"] * 0.8, 4)
        )

    def alpha_009(self) -> pd.Series:
        return self._sma(self._d["high"] - self._d["low"], 10) / self._sma(self._d["close"], 10)

    def alpha_010(self) -> pd.Series:
        return self._rank(self._ts_max(self._std_dev(self._d["returns"], 5), 5))

    def alpha_011(self) -> pd.Series:
        return self._ts_sum(
            (
                (self._d["close"] - self._d["low"]) - (self._d["high"] - self._d["close"])
            )
            / (self._d["high"] - self._d["low"] + 0.001)
            * self._d["volume"],
            6,
        )

    def alpha_012(self) -> pd.Series:
        return self._rank(self._ts_min(self._delta(self._d["vwap"], 1), 5)) * self._ts_rank(
            self._ts_max(self._std_dev(self._d["returns"], 10), 10), 5
        )

    def alpha_013(self) -> pd.Series:
        return (self._d["high"] * self._d["low"]) ** 0.5 - self._d["vwap"]

    def alpha_014(self) -> pd.Series:
        return self._d["close"] - self._delay(self._d["close"], 5)

    def alpha_015(self) -> pd.Series:
        return self._d["open"] / self._delay(self._d["close"], 1) - 1

    def alpha_016(self) -> pd.Series:
        return -1 * self._ts_max(
            self._rank(self._correlation(self._rank(self._d["volume"]), self._rank(self._d["vwap"]), 5)),
            5,
        )

    def alpha_017(self) -> pd.Series:
        return -1 * self._rank(self._ts_min(self._delta(self._d["close"], 10), 10))

    def alpha_018(self) -> pd.Series:
        return (
            self._std_dev(abs(self._d["close"] - self._d["open"]), 5)
            + (self._d["close"] - self._d["open"])
            + self._correlation(self._d["close"], self._d["open"], 10)
        )

    def alpha_019(self) -> pd.Series:
        return (
            -1
            * np.sign(self._d["close"] - self._delay(self._d["close"], 7))
            * (1 + self._rank(1 + self._ts_sum(self._d["returns"], 250)))
        )

    def alpha_020(self) -> pd.Series:
        return (
            (self._d["open"] - self._delay(self._d["high"], 1))
            * (self._d["open"] - self._delay(self._d["close"], 1))
            * (self._d["open"] - self._delay(self._d["low"], 1))
        )

    def alpha_021(self) -> pd.Series:
        return self._sma(self._d["close"], 6) / self._d["close"] - 1

    def alpha_022(self) -> pd.Series:
        return self._sma(self._d["close"] - self._sma(self._d["close"], 60), 20)

    def alpha_023(self) -> pd.Series:
        return self._sma(self._d["close"], 20)

    def alpha_024(self) -> pd.Series:
        return self._d["close"] - self._delay(self._d["close"], 6)

    def alpha_025(self) -> pd.Series:
        return -1 * self._rank(
            self._delta(self._d["close"], 7)
            * (1 - self._rank(self._decay_linear(self._d["volume"] / self._sma(self._d["volume"], 20), 9)))
        )

    def alpha_026(self) -> pd.Series:
        return self._ts_max(self._d["close"], 50) / self._d["close"]

    def alpha_027(self) -> pd.Series:
        return self._rank(
            self._correlation(self._ts_rank(self._d["volume"], 10), self._ts_rank(self._d["vwap"], 10), 6)
        )

    def alpha_028(self) -> pd.Series:
        return self._std_dev(self._d["close"], 5)

    def alpha_029(self) -> pd.Series:
        return self._ts_min(self._delta(self._d["close"], 9), 9)

    def alpha_030(self) -> pd.Series:
        return self._d["close"] - self._delay(self._d["close"], 20)

    def alpha_031(self) -> pd.Series:
        return (self._d["close"] - self._sma(self._d["close"], 10)) / self._sma(self._d["close"], 10)

    def alpha_032(self) -> pd.Series:
        return -1 * self._ts_sum(self._rank(self._correlation(self._d["high"], self._d["volume"], 5)), 5)

    def alpha_033(self) -> pd.Series:
        return self._rank(-1 * self._ts_min(self._d["low"], 5)) + self._ts_rank(
            self._delay(self._d["vwap"], 5), 5
        )

    def alpha_034(self) -> pd.Series:
        return self._sma(self._d["close"], 12) / self._d["close"]

    def alpha_035(self) -> pd.Series:
        return (
            self._ts_rank(self._d["volume"], 32)
            * (1 - self._ts_rank(self._d["close"] + self._d["high"] - self._d["low"], 16))
            * (1 - self._ts_rank(self._d["returns"], 32))
        )

    def alpha_036(self) -> pd.Series:
        return (
            2.21 * self._rank(self._correlation(self._d["close"], self._d["open"], 5))
            + 0.7 * self._rank(self._d["open"] - self._d["close"])
            + 0.73 * self._rank(self._ts_rank(self._delay(-1 * self._d["returns"], 6), 5))
            + self._rank(abs(self._correlation(self._d["vwap"], self._d["returns"], 6)))
            + 0.6 * self._rank((self._sma(self._d["close"], 200) - self._d["close"]) / self._d["close"])
        )

    def alpha_037(self) -> pd.Series:
        return self._rank(
            self._correlation(self._delay(self._d["open"] - self._d["close"], 1), self._d["close"], 200)
        ) + self._rank(self._d["open"] - self._d["close"])

    def alpha_038(self) -> pd.Series:
        return -1 * self._rank(self._ts_rank(self._d["close"], 10)) * self._rank(
            self._d["close"] / self._d["open"]
        )

    def alpha_039(self) -> pd.Series:
        return -1 * self._rank(
            self._delta(self._d["close"], 7)
            * (1 - self._rank(self._decay_linear(self._d["volume"] / self._sma(self._d["volume"], 20), 9)))
        )

    def alpha_040(self) -> pd.Series:
        return self._rank(self._d["volume"]) * self._ts_rank(self._d["close"], 5)

    def alpha_041(self) -> pd.Series:
        return -1 * self._rank(self._ts_max(self._delta(self._d["vwap"], 3), 5))

    def alpha_042(self) -> pd.Series:
        return self._rank(self._std_dev(self._d["high"], 10)) * self._correlation(
            self._d["high"], self._d["volume"], 10
        )

    def alpha_043(self) -> pd.Series:
        return self._ts_sum(self._d["close"] > self._delay(self._d["close"], 1), 6) / 6

    def alpha_044(self) -> pd.Series:
        return -1 * self._correlation(self._d["high"], self._rank(self._d["volume"]), 5)

    def alpha_045(self) -> pd.Series:
        return (
            -1
            * self._rank(self._ts_sum(self._delay(self._d["close"], 5), 20) / 20)
            * self._correlation(self._d["close"], self._d["volume"], 2)
            * self._rank(
                self._correlation(
                    self._ts_sum(self._d["close"], 5), self._ts_sum(self._d["close"], 20), 2
                )
            )
        )

    def alpha_046(self) -> pd.Series:
        return (self._delay(self._d["close"], 20) - self._delay(self._d["close"], 10)) / 10 - (
            self._delay(self._d["close"], 10) - self._d["close"]
        ) / 10

    def alpha_047(self) -> pd.Series:
        return self._sma(self._d["close"], 60) - self._d["close"]

    def alpha_048(self) -> pd.Series:
        return (
            -1
            * self._rank(
                np.sign(self._d["close"] - self._delay(self._d["close"], 1))
                + np.sign(self._delay(self._d["close"], 1) - self._delay(self._d["close"], 2))
                + np.sign(self._delay(self._d["close"], 2) - self._delay(self._d["close"], 3))
            )
            * self._ts_sum(self._d["volume"], 5)
            / self._ts_sum(self._d["volume"], 20)
        )

    def alpha_049(self) -> pd.Series:
        return self._ts_sum(
            self._d["high"] + self._d["low"] >= self._delay(self._d["high"], 1) + self._delay(self._d["low"], 1),
            20,
        ) / 20

    def alpha_050(self) -> pd.Series:
        return self._ts_sum(
            self._d["high"] + self._d["low"] <= self._delay(self._d["high"], 1) + self._delay(self._d["low"], 1),
            20,
        ) / 20

    def alpha_051(self) -> pd.Series:
        return self._ts_sum(
            self._d["high"] + self._d["low"] > self._delay(self._d["high"], 1) + self._delay(self._d["low"], 1),
            20,
        ) / 20

    def alpha_052(self) -> pd.Series:
        return self._ts_sum(self._ts_max(self._d["high"], 4), 12) / self._ts_sum(
            self._ts_min(self._d["low"], 4), 12
        )

    def alpha_053(self) -> pd.Series:
        return self._ts_sum(self._d["close"] > self._delay(self._d["close"], 1), 12) / 12

    def alpha_054(self) -> pd.Series:
        return -1 * self._rank(self._std_dev(self._d["returns"], 10))

    def alpha_055(self) -> pd.Series:
        return self._correlation(
            self._rank(
                (self._d["close"] - self._ts_min(self._d["low"], 12))
                / (self._ts_max(self._d["high"], 12) - self._ts_min(self._d["low"], 12) + 0.001)
            ),
            self._rank(self._d["volume"]),
            6,
        )

    def alpha_056(self) -> pd.Series:
        return self._rank(self._ts_max(self._d["returns"], 10))

    def alpha_057(self) -> pd.Series:
        return self._sma(self._d["close"] - self._ts_min(self._d["low"], 9), 9)

    def alpha_058(self) -> pd.Series:
        return self._ts_sum(self._d["close"] > self._delay(self._d["close"], 1), 20) / 20

    def alpha_059(self) -> pd.Series:
        return self._ts_sum((self._d["close"] - self._delay(self._d["close"], 1) < 0), 20) / 20

    def alpha_060(self) -> pd.Series:
        return self._ts_sum(
            (
                (self._d["close"] - self._d["low"]) - (self._d["high"] - self._d["close"])
            )
            / (self._d["high"] - self._d["low"] + 0.001)
            * self._d["volume"],
            20,
        )

    def alpha_061(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["vwap"], 1), 10))

    def alpha_062(self) -> pd.Series:
        return -1 * self._correlation(self._d["high"], self._d["volume"], 10)

    def alpha_063(self) -> pd.Series:
        return self._sma(self._d["close"], 20)

    def alpha_064(self) -> pd.Series:
        return self._sma(
            self._correlation(self._ts_rank(self._d["volume"], 10), self._ts_rank(self._d["vwap"], 10), 4), 10
        )

    def alpha_065(self) -> pd.Series:
        return self._sma(self._d["close"], 6) / self._d["close"]

    def alpha_066(self) -> pd.Series:
        return self._d["close"] / self._ts_max(self._d["close"], 240)

    def alpha_067(self) -> pd.Series:
        return self._sma(self._d["returns"], 5)

    def alpha_068(self) -> pd.Series:
        return self._ts_min(self._d["close"], 240) / self._d["close"]

    def alpha_069(self) -> pd.Series:
        return self._rank(self._ts_max(self._delta(self._d["vwap"], 3), 5))

    def alpha_070(self) -> pd.Series:
        return self._std_dev(self._d["turnover_rate"], 10)

    def alpha_071(self) -> pd.Series:
        return self._correlation(
            self._ts_rank(self._d["close"], 10), self._ts_rank(self._delta(self._d["close"], 3), 10), 3
        )

    def alpha_072(self) -> pd.Series:
        return self._sma(self._ts_max(self._d["high"], 6) - self._d["close"], 20) / self._sma(
            self._ts_min(self._d["low"], 6) - self._d["close"], 20
        )

    def alpha_073(self) -> pd.Series:
        return self._ts_rank(
            self._decay_linear(self._decay_linear(self._delta(self._d["close"], 1), 10), 10), 5
        ) - self._rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._sma(self._d["volume"], 30), 4), 10)
        )

    def alpha_074(self) -> pd.Series:
        return (
            self._rank(
                self._correlation(self._d["close"], self._ts_sum(self._sma(self._d["volume"], 30), 37), 15)
            )
            < self._rank(
                self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 18)
            )
        )

    def alpha_075(self) -> pd.Series:
        return self._rank(self._correlation(self._d["vwap"], self._d["volume"], 4))

    def alpha_076(self) -> pd.Series:
        return self._rank(self._delta(self._d["close"], 20))

    def alpha_077(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["close"], 3) / self._delay(self._d["close"], 3), 20))

    def alpha_078(self) -> pd.Series:
        return self._rank(
            self._correlation(
                self._ts_sum(self._d["low"], 5), self._ts_sum(self._sma(self._d["volume"], 60), 20), 7
            )
        )

    def alpha_079(self) -> pd.Series:
        return self._rank(self._delta(self._d["close"], 7))

    def alpha_080(self) -> pd.Series:
        return self._rank(np.sign(self._delta(self._d["high"], 1)))

    def alpha_081(self) -> pd.Series:
        return self._rank(np.log(self._d["vwap"] / self._d["close"]))

    def alpha_082(self) -> pd.Series:
        return self._rank(self._delta(self._d["open"], 1))

    def alpha_083(self) -> pd.Series:
        return self._rank(self._d["high"] * self._d["low"] / self._d["close"] ** 2)

    def alpha_084(self) -> pd.Series:
        return self._ts_sum(self._d["close"] / self._delay(self._d["close"], 5), 30)

    def alpha_085(self) -> pd.Series:
        return self._rank(self._correlation(self._d["close"], self._d["volume"], 10))

    def alpha_086(self) -> pd.Series:
        return -1 * self._rank(self._d["close"] / self._delay(self._d["close"], 1) - 1)

    def alpha_087(self) -> pd.Series:
        return self._rank(self._correlation(self._d["vwap"], self._delta(self._d["vwap"], 2), 6))

    def alpha_088(self) -> pd.Series:
        return self._rank(self._decay_linear(self._rank(self._d["close"]), 10))

    def alpha_089(self) -> pd.Series:
        return self._ts_rank(self._decay_linear(self._correlation(self._d["low"], self._d["volume"], 10), 7), 6)

    def alpha_090(self) -> pd.Series:
        return self._rank(self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 7))

    def alpha_091(self) -> pd.Series:
        return self._rank(self._d["close"] * self._d["volume"])

    def alpha_092(self) -> pd.Series:
        return self._rank(
            self._decay_linear(self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 4), 10)
        )

    def alpha_093(self) -> pd.Series:
        return self._ts_rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._d["volume"], 3), 5), 3
        )

    def alpha_094(self) -> pd.Series:
        return -1 * self._rank(self._d["vwap"] - self._ts_min(self._d["vwap"], 11))

    def alpha_095(self) -> pd.Series:
        return self._rank(self._d["open"] - self._sma(self._d["volume"], 10))

    def alpha_096(self) -> pd.Series:
        return self._rank(self._decay_linear(self._correlation(self._d["vwap"], self._d["returns"], 4), 7))

    def alpha_097(self) -> pd.Series:
        return self._rank(self._std_dev(self._d["close"], 10))

    def alpha_098(self) -> pd.Series:
        return self._rank(
            self._delta(self._ts_sum(self._d["close"], 100) / 100, 100) / self._delay(self._d["close"], 100)
        )

    def alpha_099(self) -> pd.Series:
        return -1 * self._rank(self._correlation(self._d["high"], self._d["volume"], 5))

    def alpha_100(self) -> pd.Series:
        return self._std_dev(self._d["volume"], 20)

    def alpha_101(self) -> pd.Series:
        return (self._d["close"] - self._d["open"]) / (self._d["high"] - self._d["low"] + 0.001)

    def alpha_102(self) -> pd.Series:
        return self._sma(self._d["volume"], 10)

    def alpha_103(self) -> pd.Series:
        return (self._ts_min(self._d["low"], 20) - self._d["low"]) / (
            self._ts_max(self._d["high"], 20) - self._ts_min(self._d["low"], 20) + 0.001
        )

    def alpha_104(self) -> pd.Series:
        return -1 * self._delta(self._correlation(self._d["high"], self._d["volume"], 5), 5)

    def alpha_105(self) -> pd.Series:
        return -1 * self._correlation(self._rank(self._d["open"]), self._rank(self._d["volume"]), 10)

    def alpha_106(self) -> pd.Series:
        return self._d["close"] - self._delay(self._d["close"], 20)

    def alpha_107(self) -> pd.Series:
        return (
            -1
            * self._rank(self._d["open"] - self._delay(self._d["high"], 1))
            * self._rank(self._d["open"] - self._delay(self._d["close"], 1))
            * self._rank(self._d["open"] - self._delay(self._d["low"], 1))
        )

    def alpha_108(self) -> pd.Series:
        return self._rank(self._correlation(self._rank(self._d["high"]), self._rank(self._d["volume"]), 3))

    def alpha_109(self) -> pd.Series:
        return self._sma(self._d["high"], 10) / self._d["high"]

    def alpha_110(self) -> pd.Series:
        return self._ts_sum(self._ts_max(self._d["high"], 10), 10) / self._ts_sum(
            self._ts_min(self._d["low"], 10), 10
        )

    def alpha_111(self) -> pd.Series:
        return self._sma(
            self._d["volume"]
            * ((self._d["close"] - self._d["low"]) - (self._d["high"] - self._d["close"]))
            / (self._d["high"] - self._d["low"] + 0.001),
            11,
        )

    def alpha_112(self) -> pd.Series:
        return self._ts_sum(self._d["close"] - self._delay(self._d["close"], 1) > 0, 12) / 12

    def alpha_113(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._delta(self._d["close"], 7), 8))

    def alpha_114(self) -> pd.Series:
        return self._rank(
            self._ts_rank(self._delay((self._d["high"] - self._d["low"]) / self._d["close"], 2), 20)
        ) * self._rank(self._ts_rank(self._correlation(self._d["close"], self._d["volume"], 6), 2))

    def alpha_115(self) -> pd.Series:
        return self._rank(self._correlation(self._d["high"] ** 2, self._d["volume"], 5))

    def alpha_116(self) -> pd.Series:
        return self._d["close"] / self._delay(self._d["close"], 10) - 1

    def alpha_117(self) -> pd.Series:
        return (
            self._ts_rank(self._d["volume"], 32)
            * (1 - self._ts_rank(self._d["close"] + self._d["high"] - self._d["low"], 16))
            * (1 - self._ts_rank(self._d["returns"], 32))
        )

    def alpha_118(self) -> pd.Series:
        return self._ts_sum(self._d["high"], 20) / 20

    def alpha_119(self) -> pd.Series:
        return self._rank(self._decay_linear(self._correlation(self._d["vwap"], self._d["volume"], 4), 7))

    def alpha_120(self) -> pd.Series:
        return self._rank(self._d["vwap"] - self._d["close"]) / self._rank(self._d["vwap"] + self._d["close"])

    def alpha_121(self) -> pd.Series:
        return self._rank(self._ts_max(self._delta(self._d["vwap"], 1), 5))

    def alpha_122(self) -> pd.Series:
        return self._sma(self._sma(self._sma(np.log(self._d["close"]), 13), 13), 13)

    def alpha_123(self) -> pd.Series:
        return self._rank(
            self._correlation(
                self._ts_sum(self._d["high"], 5), self._ts_sum(self._sma(self._d["volume"], 40), 5), 10
            )
        )

    def alpha_124(self) -> pd.Series:
        return self._d["close"] - self._d["vwap"]

    def alpha_125(self) -> pd.Series:
        return self._rank(self._decay_linear(self._correlation(self._d["vwap"], self._d["returns"], 4), 7))

    def alpha_126(self) -> pd.Series:
        return self._d["close"] / self._delay(self._d["close"], 20)

    def alpha_127(self) -> pd.Series:
        return self._rank(self._sma(self._d["volume"], 10))

    def alpha_128(self) -> pd.Series:
        return 100 - self._ts_rank(self._ts_sum(self._d["close"], 10), 10)

    def alpha_129(self) -> pd.Series:
        return self._ts_sum(self._d["close"] - self._delay(self._d["close"], 1) < 0, 12) / 12

    def alpha_130(self) -> pd.Series:
        return self._rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._d["volume"], 10), 10)
        )

    def alpha_131(self) -> pd.Series:
        return self._rank(self._delta(self._d["vwap"], 1))

    def alpha_132(self) -> pd.Series:
        return self._sma(self._d["turnover"], 20)

    def alpha_133(self) -> pd.Series:
        return self._ts_rank(self._d["close"], 10)

    def alpha_134(self) -> pd.Series:
        return self._d["close"] / self._delay(self._d["close"], 12) - 1

    def alpha_135(self) -> pd.Series:
        return self._sma(self._delta(self._d["close"], 3), 20)

    def alpha_136(self) -> pd.Series:
        return -1 * self._rank(self._delta(self._d["returns"], 3)) * self._correlation(
            self._d["open"], self._d["volume"], 10
        )

    def alpha_137(self) -> pd.Series:
        return -1 * self._rank(self._d["open"] - self._delay(self._d["open"], 1))

    def alpha_138(self) -> pd.Series:
        return self._ts_rank(self._delay(self._d["close"] / self._d["high"], 2), 5)

    def alpha_139(self) -> pd.Series:
        return -1 * self._correlation(self._d["open"], self._d["volume"], 10)

    def alpha_140(self) -> pd.Series:
        return self._ts_min(self._rank(self._rank(np.log(self._d["volume"]))), 5)

    def alpha_141(self) -> pd.Series:
        return self._rank(self._correlation(self._rank(self._d["high"]), self._rank(self._d["volume"]), 3))

    def alpha_142(self) -> pd.Series:
        return (
            -1
            * self._rank(self._ts_rank(self._d["close"], 10))
            * self._rank(self._delta(self._delta(self._d["close"], 1), 1))
            * self._rank(self._ts_rank(self._d["volume"] / self._sma(self._d["volume"], 20), 5))
        )

    def alpha_143(self) -> pd.Series:
        return self._d["close"] > self._delay(self._d["close"], 1)

    def alpha_144(self) -> pd.Series:
        return self._ts_sum(
            self._d["close"] / self._delay(self._d["close"], 1)
            - 1
            - self._sma(self._d["close"] / self._delay(self._d["close"], 1) - 1, 61),
            20,
        )

    def alpha_145(self) -> pd.Series:
        return self._sma(self._d["volume"], 9) - self._sma(self._d["volume"], 26)

    def alpha_146(self) -> pd.Series:
        return self._sma(self._d["close"] / self._delay(self._d["close"], 1) - 1, 61)

    def alpha_147(self) -> pd.Series:
        return self._ts_rank(self._correlation(self._rank(self._d["close"]), self._rank(self._d["volume"]), 4), 4)

    def alpha_148(self) -> pd.Series:
        return self._rank(self._correlation(self._delay(self._d["open"], 1), self._d["volume"], 10))

    def alpha_149(self) -> pd.Series:
        return self._rank(self._correlation(self._d["open"], self._d["volume"], 10))

    def alpha_150(self) -> pd.Series:
        return (self._d["open"] + self._d["high"] + self._d["low"] + self._d["close"]) / 4

    def alpha_151(self) -> pd.Series:
        return self._sma(self._d["close"] - self._delay(self._d["close"], 1), 20)

    def alpha_152(self) -> pd.Series:
        return self._sma(self._sma(self._d["close"] / self._delay(self._d["close"], 20) - 1, 20), 20)

    def alpha_153(self) -> pd.Series:
        return self._d["close"] / self._delay(self._d["close"], 3) - 1

    def alpha_154(self) -> pd.Series:
        return (self._d["vwap"] - self._ts_min(self._d["vwap"], 15)) * self._rank(
            self._correlation(self._d["vwap"], self._sma(self._d["volume"], 40), 17)
        )

    def alpha_155(self) -> pd.Series:
        return self._sma(self._d["volume"], 13) - self._sma(self._d["volume"], 27)

    def alpha_156(self) -> pd.Series:
        return self._ts_rank(
            self._decay_linear(
                self._rank(self._d["open"])
                + self._rank(self._d["low"])
                - self._rank(self._d["high"])
                - self._rank(self._d["close"]),
                8,
            ),
            7,
        )

    def alpha_157(self) -> pd.Series:
        return self._ts_min(self._d["close"], 20)

    def alpha_158(self) -> pd.Series:
        return (self._d["high"] - self._d["low"]) / self._d["close"]

    def alpha_159(self) -> pd.Series:
        return (self._d["close"] - self._ts_sum(self._d["close"], 6)) / 6 + (
            self._d["close"] - self._ts_sum(self._d["close"], 24)
        ) / 24

    def alpha_160(self) -> pd.Series:
        return self._sma(self._d["close"] <= self._delay(self._d["close"], 1), 20)

    def alpha_161(self) -> pd.Series:
        return self._ts_max(self._d["close"], 10)

    def alpha_162(self) -> pd.Series:
        return self._sma(self._ts_max(self._d["close"], 12) - self._ts_min(self._d["close"], 12), 12)

    def alpha_163(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["close"], 5), 3))

    def alpha_164(self) -> pd.Series:
        return self._sma(self._d["close"] > self._delay(self._d["close"], 1), 10)

    def alpha_165(self) -> pd.Series:
        return self._ts_max(self._d["close"], 240) - self._ts_min(self._d["close"], 240)

    def alpha_166(self) -> pd.Series:
        return -20 * self._sma(self._d["close"] / self._delay(self._d["close"], 20) - 1, 20)

    def alpha_167(self) -> pd.Series:
        return self._ts_sum(self._d["close"] - self._delay(self._d["close"], 1) > 0, 20)

    def alpha_168(self) -> pd.Series:
        return -1 * self._d["volume"] / self._sma(self._d["volume"], 20)

    def alpha_169(self) -> pd.Series:
        return self._sma(self._d["close"], 20)

    def alpha_170(self) -> pd.Series:
        return (
            self._rank(1 / self._d["close"])
            * self._d["volume"]
            / self._sma(self._d["volume"], 20)
            * (self._d["high"] * self._rank(self._d["high"] - self._d["close"]))
            / self._ts_sum(self._d["high"], 5)
        )

    def alpha_171(self) -> pd.Series:
        return (
            -1
            * (self._d["low"] - self._d["close"])
            * (self._d["open"] ** 5)
            / ((self._d["close"] - self._d["open"]) ** 2)
        )

    def alpha_172(self) -> pd.Series:
        return self._sma(self._correlation(self._d["high"], self._d["low"], 4), 10)

    def alpha_173(self) -> pd.Series:
        return (
            3 * self._sma(self._d["close"], 13)
            - 2 * self._sma(self._sma(self._d["close"], 13), 13)
            - self._sma(self._sma(self._sma(self._d["close"], 13), 13), 13)
        )

    def alpha_174(self) -> pd.Series:
        return self._sma(self._d["close"], 39)

    def alpha_175(self) -> pd.Series:
        return self._sma(self._d["close"], 13)

    def alpha_176(self) -> pd.Series:
        return self._correlation(self._rank(self._d["close"]), self._rank(self._d["volume"]), 5)

    def alpha_177(self) -> pd.Series:
        return self._ts_min(self._d["low"], 30)

    def alpha_178(self) -> pd.Series:
        return self._d["close"] / self._delay(self._d["close"], 5)

    def alpha_179(self) -> pd.Series:
        return self._rank(self._correlation(self._d["vwap"], self._d["open"], 18))

    def alpha_180(self) -> pd.Series:
        return self._rank(self._d["volume"])

    def alpha_181(self) -> pd.Series:
        return self._rank(self._correlation(self._d["low"], self._d["open"], 10))

    def alpha_182(self) -> pd.Series:
        return self._ts_sum(self._d["open"] > self._delay(self._d["open"], 1), 20)

    def alpha_183(self) -> pd.Series:
        return self._rank(self._correlation(self._d["close"], self._d["open"], 10))

    def alpha_184(self) -> pd.Series:
        return self._rank(self._correlation(self._d["low"], self._d["volume"], 6))

    def alpha_185(self) -> pd.Series:
        return self._rank(-1 * (self._d["close"] - self._delay(self._d["close"], 7)))

    def alpha_186(self) -> pd.Series:
        return self._ts_sum(self._d["open"], 21) / 21 - self._ts_sum(self._d["open"], 63) / 63

    def alpha_187(self) -> pd.Series:
        return self._ts_sum(self._d["open"] <= self._delay(self._d["open"], 1), 20)

    def alpha_188(self) -> pd.Series:
        return (self._d["high"] - self._d["low"]) / self._sma(self._d["close"], 50)

    def alpha_189(self) -> pd.Series:
        return self._sma(self._d["close"], 26) - self._sma(self._d["close"], 12)

    def alpha_190(self) -> pd.Series:
        return np.log(self._ts_sum(self._d["volume"], 20))

    def alpha_191(self) -> pd.Series:
        return self._correlation(self._sma(self._d["vwap"], 20), self._sma(self._d["volume"], 20), 18)

    # ------------------------------------------------------------------
    # WorldQuant Alpha 101 factors
    # ------------------------------------------------------------------

    def wq_alpha_001(self) -> pd.Series:
        inner = self._d["close"].copy()
        inner[self._d["returns"] < 0] = self._std_dev(self._d["returns"], 20)
        return self._rank(self._ts_argmax(inner**2, 5))

    def wq_alpha_002(self) -> pd.Series:
        p1 = self._rank(self._delta(np.log(self._d["volume"]), 2))
        p2 = self._rank((self._d["close"] - self._d["open"]) / self._d["open"])
        return -1 * self._correlation(p1, p2, 6)

    def wq_alpha_003(self) -> pd.Series:
        p1 = self._rank(self._d["open"])
        p2 = self._rank(self._d["volume"])
        return -1 * self._correlation(p1, p2, 10)

    def wq_alpha_004(self) -> pd.Series:
        return -1 * self._ts_rank(self._rank(self._d["low"]), 9)

    def wq_alpha_005(self) -> pd.Series:
        return self._rank(self._d["open"] - self._ts_min(self._d["open"], 10)) - self._rank(
            self._rank(self._d["close"]) - self._ts_min(self._d["close"], 10)
        )

    def wq_alpha_006(self) -> pd.Series:
        return -1 * self._correlation(self._d["open"], self._d["volume"], 10)

    def wq_alpha_007(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        alpha = -1 * self._ts_rank(abs(self._delta(self._d["close"], 7)), 60) * np.sign(
            self._delta(self._d["close"], 7)
        )
        alpha[adv20 >= self._d["volume"]] = -1
        return alpha

    def wq_alpha_008(self) -> pd.Series:
        term = self._ts_sum(self._d["open"], 5) * self._ts_sum(self._d["returns"], 5)
        return -1 * self._rank(term - self._delay(term, 10))

    def wq_alpha_009(self) -> pd.Series:
        delta_close = self._delta(self._d["close"], 1)
        cond_1 = self._ts_min(delta_close, 5) > 0
        cond_2 = self._ts_max(delta_close, 5) < 0
        alpha = -1 * delta_close
        alpha[cond_1 | cond_2] = delta_close
        return alpha

    def wq_alpha_010(self) -> pd.Series:
        delta_close = self._delta(self._d["close"], 1)
        cond_1 = self._ts_min(delta_close, 4) > 0
        cond_2 = self._ts_max(delta_close, 4) < 0
        alpha = -1 * delta_close
        alpha[cond_1 | cond_2] = delta_close
        return alpha

    def wq_alpha_011(self) -> pd.Series:
        return (
            self._rank(self._ts_max(self._d["vwap"] - self._d["close"], 3))
            + self._rank(self._ts_min(self._d["vwap"] - self._d["close"], 3))
        ) * self._rank(self._delta(self._d["volume"], 3))

    def wq_alpha_012(self) -> pd.Series:
        return np.sign(self._delta(self._d["volume"], 1)) * (-1 * self._delta(self._d["close"], 1))

    def wq_alpha_013(self) -> pd.Series:
        return -1 * self._rank(self._covariance(self._rank(self._d["close"]), self._rank(self._d["volume"]), 5))

    def wq_alpha_014(self) -> pd.Series:
        return -1 * self._rank(self._delta(self._d["returns"], 3)) * self._correlation(
            self._d["open"], self._d["volume"], 10
        )

    def wq_alpha_015(self) -> pd.Series:
        return -1 * self._ts_sum(
            self._rank(self._correlation(self._rank(self._d["high"]), self._rank(self._d["volume"]), 3)), 3
        )

    def wq_alpha_016(self) -> pd.Series:
        return -1 * self._rank(self._covariance(self._rank(self._d["high"]), self._rank(self._d["volume"]), 5))

    def wq_alpha_017(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        return (
            -1
            * self._rank(self._ts_rank(self._d["close"], 10))
            * self._rank(self._delta(self._delta(self._d["close"], 1), 1))
            * self._rank(self._ts_rank(self._d["volume"] / adv20, 5))
        )

    def wq_alpha_018(self) -> pd.Series:
        return -1 * self._rank(
            self._std_dev(abs(self._d["close"] - self._d["open"]), 5)
            + (self._d["close"] - self._d["open"])
            + self._correlation(self._d["close"], self._d["open"], 10)
        )

    def wq_alpha_019(self) -> pd.Series:
        return -1 * np.sign(self._d["close"] - self._delay(self._d["close"], 7)) + self._rank(
            self._ts_cumprod(self._d["returns"])
        )

    def wq_alpha_020(self) -> pd.Series:
        return (
            -1
            * self._rank(self._d["open"] - self._delay(self._d["high"], 1))
            * self._rank(self._d["open"] - self._delay(self._d["close"], 1))
            * self._rank(self._d["open"] - self._delay(self._d["low"], 1))
        )

    def wq_alpha_021(self) -> pd.Series:
        cond1 = self._sma(self._d["close"], 8) + self._std_dev(self._d["close"], 8) < self._sma(
            self._d["close"], 2
        )
        cond2 = self._sma(self._d["volume"], 20) / self._d["volume"] < 1
        alpha = pd.Series(np.ones_like(self._d["close"]), index=self._index)
        alpha[cond1 | cond2] = -1
        return alpha

    def wq_alpha_022(self) -> pd.Series:
        return -1 * self._delta(self._correlation(self._d["high"], self._d["volume"], 5), 5) * self._rank(
            self._std_dev(self._d["close"], 20)
        )

    def wq_alpha_023(self) -> pd.Series:
        cond = self._sma(self._d["high"], 20) < self._d["high"]
        alpha = pd.Series(np.zeros_like(self._d["close"]), index=self._index)
        alpha[cond] = -self._delta(self._d["high"], 2)
        return alpha

    def wq_alpha_024(self) -> pd.Series:
        cond = self._delta(self._sma(self._d["close"], 100), 100) / self._delay(self._d["close"], 100) <= 0.05
        alpha = -1 * self._delta(self._d["close"], 3)
        alpha[cond] = -1 * (self._d["close"] - self._ts_min(self._d["close"], 100))
        return alpha

    def wq_alpha_025(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        return -1 * self._rank(
            (-1 * self._d["returns"]) * adv20 * self._d["vwap"] * (self._d["high"] - self._d["close"])
        )

    def wq_alpha_026(self) -> pd.Series:
        return -1 * self._ts_max(
            self._correlation(self._ts_rank(self._d["volume"], 5), self._ts_rank(self._d["high"], 5), 5), 3
        )

    def wq_alpha_027(self) -> pd.Series:
        alpha = self._rank(
            (self._sma(self._d["volume"], 10) - self._sma(self._d["volume"], 20)) / self._sma(self._d["volume"], 60)
        )
        return alpha * -1

    def wq_alpha_028(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        return self._scale(
            (self._correlation(adv20, self._d["low"], 5) + ((self._d["high"] + self._d["low"]) / 2))
            - self._d["close"]
        )

    def wq_alpha_029(self) -> pd.Series:
        return self._ts_min(
            self._rank(
                self._rank(
                    self._scale(np.log(self._ts_sum(self._rank(self._rank(-1 * self._rank(self._delta(self._d["close"] - 1, 5)))), 2)))
                )
            ),
            5,
        ) + self._ts_rank(self._delay(-1 * self._d["returns"], 6), 5)

    def wq_alpha_030(self) -> pd.Series:
        delta_close = self._delta(self._d["close"], 1)
        return (
            1.0
            - self._rank(
                np.sign(delta_close) + np.sign(self._delay(delta_close, 1)) + np.sign(self._delay(delta_close, 2))
            )
        ) * self._ts_sum(self._d["volume"], 5) / self._ts_sum(self._d["volume"], 20)

    def wq_alpha_031(self) -> pd.Series:
        return (
            self._rank(self._rank(self._rank(self._decay_linear(-1 * self._rank(self._rank(self._delta(self._d["close"], 10))), 10))))
            + self._rank(-1 * self._delta(self._d["close"], 3))
            + np.sign(self._scale(self._correlation(self._sma(self._d["volume"], 20), self._d["low"], 12)))
        )

    def wq_alpha_032(self) -> pd.Series:
        return self._scale(
            (self._sma(self._d["close"], 7) - self._d["close"])
            + (self._ts_min(self._d["close"], 180) - self._d["close"])
        )

    def wq_alpha_033(self) -> pd.Series:
        return self._rank(-1 * (1 - (self._d["open"] / self._d["close"])))

    def wq_alpha_034(self) -> pd.Series:
        return self._rank(
            (1 - self._rank(self._std_dev(self._d["returns"], 2) / self._std_dev(self._d["returns"], 5)))
            + (1 - self._rank(self._delta(self._d["close"], 1)))
        )

    def wq_alpha_035(self) -> pd.Series:
        return (
            self._ts_rank(self._d["volume"], 32)
            * (1 - self._ts_rank(self._d["close"] + self._d["high"] - self._d["low"], 16))
            * (1 - self._ts_rank(self._d["returns"], 32))
        )

    def wq_alpha_036(self) -> pd.Series:
        return self._rank(self._correlation(self._d["open"], self._d["volume"], 10))

    def wq_alpha_037(self) -> pd.Series:
        return -1 * self._rank(self._ts_sum(self._d["open"], 5)) * self._rank(self._d["returns"])

    def wq_alpha_038(self) -> pd.Series:
        return -1 * self._rank(self._ts_rank(self._d["close"], 10)) * self._rank(self._d["close"] / self._d["open"])

    def wq_alpha_039(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        return -1 * self._rank(
            self._delta(self._d["close"], 7) * (1 - self._rank(self._decay_linear(self._d["volume"] / adv20, 9)))
        )

    def wq_alpha_040(self) -> pd.Series:
        return -1 * self._rank(self._std_dev(self._d["high"], 10)) * self._correlation(
            self._d["high"], self._d["volume"], 10
        )

    def wq_alpha_041(self) -> pd.Series:
        return pow(self._d["high"] * self._d["low"], 0.5) - self._d["vwap"]

    def wq_alpha_042(self) -> pd.Series:
        return self._rank(self._d["vwap"] - self._d["close"]) / self._rank(self._d["vwap"] + self._d["close"])

    def wq_alpha_043(self) -> pd.Series:
        adv20 = self._sma(self._d["volume"], 20)
        return self._ts_rank(self._d["volume"] / adv20, 20) * self._ts_rank(-1 * self._delta(self._d["close"], 7), 8)

    def wq_alpha_044(self) -> pd.Series:
        return -1 * self._correlation(self._d["high"], self._rank(self._d["volume"]), 5)

    def wq_alpha_045(self) -> pd.Series:
        return (
            -1
            * self._rank(self._ts_sum(self._delay(self._d["close"], 5), 20) / 20)
            * self._correlation(self._d["close"], self._d["volume"], 2)
            * self._rank(
                self._correlation(self._ts_sum(self._d["close"], 5), self._ts_sum(self._d["close"], 20), 2)
            )
        )

    def wq_alpha_046(self) -> pd.Series:
        return -1 * self._rank(self._sma(self._d["close"], 10))

    def wq_alpha_047(self) -> pd.Series:
        return self._rank(self._ts_max(self._d["high"], 10) - self._d["close"]) * -1

    def wq_alpha_048(self) -> pd.Series:
        return (
            -1
            * self._rank(
                np.sign(self._d["close"] - self._delay(self._d["close"], 1))
                + np.sign(self._delay(self._d["close"], 1) - self._delay(self._d["close"], 2))
                + np.sign(self._delay(self._d["close"], 2) - self._delay(self._d["close"], 3))
            )
            * self._ts_sum(self._d["volume"], 5)
            / self._ts_sum(self._d["volume"], 20)
        )

    def wq_alpha_049(self) -> pd.Series:
        return -1 * self._rank(self._d["close"] - self._ts_max(self._d["close"], 10))

    def wq_alpha_050(self) -> pd.Series:
        return -1 * self._ts_max(
            self._rank(self._correlation(self._rank(self._d["volume"]), self._rank(self._d["vwap"]), 5)), 5
        )

    def wq_alpha_051(self) -> pd.Series:
        return -1 * self._rank(self._d["close"] - self._ts_min(self._d["close"], 10))

    def wq_alpha_052(self) -> pd.Series:
        return -1 * self._delta(self._ts_min(self._d["low"], 5), 5)

    def wq_alpha_053(self) -> pd.Series:
        return -1 * self._delta(self._d["close"], 1)

    def wq_alpha_054(self) -> pd.Series:
        return -1 * (
            self._rank(self._d["low"] - self._d["close"])
            * self._rank(self._correlation(self._d["vwap"], self._delay(self._d["vwap"], 4), 18))
        )

    def wq_alpha_055(self) -> pd.Series:
        return -1 * self._correlation(
            self._rank(
                (self._d["close"] - self._ts_min(self._d["low"], 12))
                / (self._ts_max(self._d["high"], 12) - self._ts_min(self._d["low"], 12))
            ),
            self._rank(self._d["volume"]),
            6,
        )

    def wq_alpha_056(self) -> pd.Series:
        return -1 * self._rank(
            (self._sma(self._d["volume"], 10) - self._sma(self._d["volume"], 20)) / self._sma(self._d["volume"], 60)
        )

    def wq_alpha_057(self) -> pd.Series:
        return -1 * self._rank(self._sma(self._d["close"] - self._ts_min(self._d["low"], 9), 9))

    def wq_alpha_058(self) -> pd.Series:
        return -1 * self._ts_rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._d["volume"], 4), 7), 6
        )

    def wq_alpha_059(self) -> pd.Series:
        return -1 * self._ts_rank(
            self._decay_linear(self._rank(self._d["close"] - self._ts_max(self._d["close"], 10)), 10), 8
        )

    def wq_alpha_060(self) -> pd.Series:
        return -1 * (
            2 * self._scale(self._rank(((self._d["close"] - self._d["low"]) - (self._d["high"] - self._d["close"])) / (self._d["high"] - self._d["low"])))
            - self._scale(self._rank(self._ts_argmax(self._d["close"], 10)))
        )

    def wq_alpha_061(self) -> pd.Series:
        return self._rank(self._d["vwap"] - self._ts_min(self._d["vwap"], 16)) < self._rank(
            self._correlation(self._d["vwap"], self._sma(self._d["volume"], 180), 18)
        )

    def wq_alpha_062(self) -> pd.Series:
        return -1 * self._correlation(self._d["vwap"], self._ts_sum(self._sma(self._d["volume"], 60), 20), 20)

    def wq_alpha_063(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["close"], 1), 2))

    def wq_alpha_064(self) -> pd.Series:
        return self._rank(
            self._decay_linear(
                self._correlation(self._ts_rank(self._d["volume"], 10), self._ts_rank(self._d["vwap"], 10), 6), 4
            )
        )

    def wq_alpha_065(self) -> pd.Series:
        return self._rank(self._decay_linear(self._correlation(self._d["open"], self._d["volume"], 10), 7))

    def wq_alpha_066(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._delta(self._d["vwap"], 3), 10))

    def wq_alpha_067(self) -> pd.Series:
        return self._rank(self._ts_max(self._d["close"], 3))

    def wq_alpha_068(self) -> pd.Series:
        return self._ts_rank(self._correlation(self._rank(self._d["high"]), self._rank(self._d["volume"]), 5), 13)

    def wq_alpha_069(self) -> pd.Series:
        return self._rank(self._ts_max(self._delta(self._d["vwap"], 2), 5)) * -1

    def wq_alpha_070(self) -> pd.Series:
        return -1 * self._rank(self._delta(self._d["close"], 1))

    def wq_alpha_071(self) -> pd.Series:
        return (
            self._rank(self._ts_max(self._d["close"], 240)) - self._rank(self._ts_min(self._d["close"], 240))
        ) * self._rank(self._correlation(self._d["close"], self._d["volume"], 180))

    def wq_alpha_072(self) -> pd.Series:
        return self._rank(self._decay_linear(self._correlation(self._d["high"], self._d["volume"], 10), 10))

    def wq_alpha_073(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._delta(self._d["vwap"], 4), 3))

    def wq_alpha_074(self) -> pd.Series:
        return (
            self._rank(
                self._correlation(self._d["close"], self._ts_sum(self._sma(self._d["volume"], 30), 37), 15)
            )
            < self._rank(
                self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 18)
            )
        )

    def wq_alpha_075(self) -> pd.Series:
        return self._rank(self._correlation(self._d["vwap"], self._d["volume"], 4))

    def wq_alpha_076(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["close"], 1), 20))

    def wq_alpha_077(self) -> pd.Series:
        return self._rank(
            self._decay_linear(
                ((self._d["high"] + self._d["low"]) / 2 + self._d["high"]) - (self._d["vwap"] + self._d["high"]), 20
            )
        )

    def wq_alpha_078(self) -> pd.Series:
        return self._rank(
            self._correlation(
                self._ts_sum(self._d["low"], 5), self._ts_sum(self._sma(self._d["volume"], 60), 20), 7
            )
        )

    def wq_alpha_079(self) -> pd.Series:
        return self._rank(self._delta(self._d["close"], 2))

    def wq_alpha_080(self) -> pd.Series:
        return -1 * self._rank(np.sign(self._delta(self._d["open"], 4)))

    def wq_alpha_081(self) -> pd.Series:
        return -1 * self._rank(np.log(self._d["vwap"] / self._ts_sum(self._d["vwap"], 5)))

    def wq_alpha_082(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._d["open"], 10))

    def wq_alpha_083(self) -> pd.Series:
        return -1 * self._rank(self._d["high"] * self._d["low"])

    def wq_alpha_084(self) -> pd.Series:
        return self._ts_rank(self._d["vwap"] - self._ts_max(self._d["vwap"], 15), 20)

    def wq_alpha_085(self) -> pd.Series:
        return self._rank(self._correlation(self._d["close"], self._d["volume"], 10))

    def wq_alpha_086(self) -> pd.Series:
        return -1 * self._rank(self._correlation(self._d["close"], self._d["open"], 10))

    def wq_alpha_087(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._delta(self._d["close"], 2), 8))

    def wq_alpha_088(self) -> pd.Series:
        return self._rank(self._decay_linear(self._rank(self._d["close"]), 5)) - self._rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._d["returns"], 5), 5)
        )

    def wq_alpha_089(self) -> pd.Series:
        return -1 * self._rank(self._sma(self._d["close"], 13))

    def wq_alpha_090(self) -> pd.Series:
        return -1 * self._rank(self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 5))

    def wq_alpha_091(self) -> pd.Series:
        return -1 * self._rank(self._d["close"] * self._d["volume"])

    def wq_alpha_092(self) -> pd.Series:
        return self._rank(
            self._decay_linear(self._correlation(self._rank(self._d["vwap"]), self._rank(self._d["volume"]), 4), 10)
        )

    def wq_alpha_093(self) -> pd.Series:
        return self._ts_rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._d["volume"], 3), 5), 3
        )

    def wq_alpha_094(self) -> pd.Series:
        adv30 = self._sma(self._d["volume"], 30)
        return -1 * self._rank(self._d["vwap"] - self._ts_min(self._d["vwap"], 11)) * self._ts_rank(
            self._correlation(self._ts_rank(self._d["vwap"], 20), self._ts_rank(adv30, 50), 12), 7
        )

    def wq_alpha_095(self) -> pd.Series:
        return self._rank(self._d["open"] - self._ts_min(self._d["open"], 12)) * self._ts_rank(
            self._correlation(self._ts_sum(self._d["volume"], 40), self._d["low"], 12), 12
        )

    def wq_alpha_096(self) -> pd.Series:
        return -1 * self._rank(self._decay_linear(self._correlation(self._d["vwap"], self._d["returns"], 4), 7))

    def wq_alpha_097(self) -> pd.Series:
        return self._rank(self._decay_linear(self._delta(self._d["close"], 1), 5))

    def wq_alpha_098(self) -> pd.Series:
        return self._rank(
            self._decay_linear(self._correlation(self._d["vwap"], self._sma(self._d["volume"], 5), 3), 3)
        )

    def wq_alpha_099(self) -> pd.Series:
        return -1 * self._rank(self._covariance(self._rank(self._d["close"]), self._rank(self._d["volume"]), 5))

    def wq_alpha_100(self) -> pd.Series:
        return -1 * self._rank(self._correlation(self._d["close"], self._d["volume"], 10))

    def wq_alpha_101(self) -> pd.Series:
        return -1 * self._rank(self._correlation(self._d["close"], self._d["open"], 10))


GTJA191_METHODS = [f"alpha_{idx:03d}" for idx in range(1, ALPHA191_COUNT + 1)]
WQ101_METHODS = [f"wq_alpha_{idx:03d}" for idx in range(1, ALPHA101_COUNT + 1)]


def _compute_family(
    frame: pd.DataFrame,
    method_names: list[str],
    prefix: str,
    *,
    adjusted: bool,
    dtype: str | None,
    show_progress: bool = False,
) -> pd.DataFrame:
    normalized_dtype = normalize_factor_dtype(dtype) if dtype is not None else None
    context = ClassicAlphaContext(frame, use_adjusted_prices=bool(adjusted))
    index = context._index
    columns: dict[str, pd.Series] = {}
    for method_name in method_names:
        if show_progress:
            print(f"[classic:{prefix}] computing {method_name}", file=sys.stderr, flush=True)
        columns[method_name] = getattr(context, method_name)()
    out = pd.DataFrame(columns, index=index)
    out.columns = [f"{prefix}_{method_name.rsplit('_', 1)[-1]}" for method_name in out.columns]
    if normalized_dtype is not None:
        out = out.astype(normalized_dtype)
    return out


def build_alpha191_features(
    frame: pd.DataFrame,
    *,
    adjusted: bool = True,
    dtype: str | None = "float32",
    show_progress: bool = False,
) -> pd.DataFrame:
    """Build GTJA Alpha191 cross-sectional features as a (date, ticker) frame."""
    return _compute_family(
        frame,
        GTJA191_METHODS,
        "alpha191",
        adjusted=adjusted,
        dtype=dtype,
        show_progress=show_progress,
    )


def build_alpha101_features(
    frame: pd.DataFrame,
    *,
    adjusted: bool = True,
    dtype: str | None = "float32",
    show_progress: bool = False,
) -> pd.DataFrame:
    """Build WorldQuant Alpha101 cross-sectional features as a (date, ticker) frame."""
    return _compute_family(
        frame,
        WQ101_METHODS,
        "alpha101",
        adjusted=adjusted,
        dtype=dtype,
        show_progress=show_progress,
    )


def build_classic_alpha_features(
    frame: pd.DataFrame,
    families: Iterable[str],
    *,
    adjusted: bool = True,
    dtype: str | None = "float32",
    show_progress: bool = False,
) -> pd.DataFrame:
    """Build selected Alpha191/Alpha101 families and concat them into one frame."""
    normalized = [str(family).strip().lower().replace("-", "_") for family in families]
    supported = ("alpha101", "alpha191")
    unsupported = [family for family in normalized if family not in supported]
    if unsupported:
        choices = ", ".join(supported)
        raise ValueError(
            f"Unsupported classic alpha family: {', '.join(unsupported)}. Expected one of: {choices}."
        )
    frames: list[pd.DataFrame] = []
    for family in dict.fromkeys(normalized):
        if family == "alpha101":
            frames.append(build_alpha101_features(frame, adjusted=adjusted, dtype=dtype, show_progress=show_progress))
        else:
            frames.append(build_alpha191_features(frame, adjusted=adjusted, dtype=dtype, show_progress=show_progress))
    return pd.concat(frames, axis=1)
