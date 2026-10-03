# Publication audit

[Chinese version](https://runchengxie.github.io/money-trees/zh-CN/publication-audit/)

Before a public snapshot enters `quant-factor-observatory` or GitHub Pages, verify that:

1. `kind` is `moneytree_factor_evidence_snapshot` and `schema_version` is supported. Schema 1.1 producers record annual slices, available benchmark regimes, target holding period, HAC method, and BY/BH correction scope.
2. Every number is standard JSON; non-finite values are represented as `null`.
3. The snapshot contains no ticker, holding, weight, raw path, or credential fields.
4. The snapshot records the data version, sample interval, code revision when available, and computation configuration.
5. The input panel, raw cache, factor store, and backtest artifacts stay out of the public repository.
6. Benchmark source values are realized daily returns, agree within each date, and do not reuse the forward target; regime labels use only the prior 252 trading days.
7. Holding-period metadata matches the target construction; absent metadata leaves uncertainty and multiple-testing results `not_provided`.

Recommended flow:

```text
Private disk / research environment
        ↓
Factor generation and evidence computation
        ↓
Public-field audit
        ↓
Static JSON snapshot
        ↓
quant-factor-observatory / GitHub Pages
```

GitHub-hosted Actions only build reviewed documentation and the static frontend. They do not access the private disk and do not run research computations that require real data or credentials.
