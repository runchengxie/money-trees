# Research methodology and evidence boundaries

[中文页面](research-methodology.zh-CN.md)

Money Trees computes factors and produces aggregated evidence. Formal portfolio construction, execution simulation, and risk attribution belong to `quant-platform` and `quant-backtest-runtime`. Every research result must be bound to an explicit information set; data that was not observable at the decision point must not enter features, labels, or decisions.

## Minimum research contract

Each run should record:

- data version, source manifest SHA-256, and code revision;
- feature cutoff, publication cutoff, decision time, and execution time;
- training interval, label interval, prediction horizon, purge window, and embargo;
- candidate-factor count, tuning count, whether holdout results were viewed, and the stopping reason.

## Time-series validation

With overlapping labels, ordinary random cross-validation can leak test-label information into the training interval. Formal validation should use time-ordered walk-forward folds, remove training events whose labels overlap the test labels, and then apply an embargo. Money Trees can produce candidate-factor evidence; the shared purge/embargo implementation and validation receipt belong to `quant-platform`.

## Uncertainty and tail risk

Average IC or cumulative return is not sufficient evidence. Formal reports should include block bootstrap or another dependence-aware uncertainty estimate, effective sample size, maximum drawdown, VaR/CVaR, and cost sensitivity where possible. Without those diagnostics, `factor_evidence.v1` marks the corresponding sections `not_provided` and does not interpret missing diagnostics as a pass.

The public Alpha evidence producer estimates uncertainty for mean daily RankIC with Newey–West HAC when the forward-return holding period is explicit. The lag is the holding period minus one trading day, missing dates retain their positions, and the interval uses a two-sided standard-normal reference. Across the declared factor family, Benjamini–Yekutieli is the primary false-discovery adjustment; unavailable tests remain in the denominator and do not receive q-values. These tests concern predictive RankIC only and do not replace portfolio-level risk, cost, or execution analysis.

## Residuals and publication

After controlling for size, volatility, liquidity, or industry exposure, factor residual predictability still needs to be checked. The public site accepts aggregated results only; it does not accept per-security signals, portfolio weights, raw paths, or vendor fields. `factor_evidence.v1` is the shared aggregated contract between the research layer and Observatory.
