# Publication audit

[中文页面](publication-audit.zh-CN.md)

Before a public snapshot enters `quant-factor-observatory` or GitHub Pages, verify that:

1. `kind` is `moneytree_factor_evidence_snapshot` and `schema_version` is supported.
2. Every number is standard JSON; non-finite values are represented as `null`.
3. The snapshot contains no ticker, holding, weight, raw path, or credential fields.
4. The snapshot records the data version, sample interval, code revision when available, and computation configuration.
5. The input panel, raw cache, factor store, and backtest artifacts stay out of the public repository.

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
