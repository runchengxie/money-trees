# Documentation language status

[简体中文](https://runchengxie.github.io/money-trees/zh-CN/language-migration-status/)

The MkDocs site defaults to English at the existing root URLs. Chinese pages live under `/zh-CN/`, with the same page slug. Each locale has its own navigation and search index. The language selector opens the matching page. Chinese search uses Material for MkDocs' `zh` search language and Jieba segmentation. Old `*.zh-CN/` URLs redirect to the new Chinese routes. Every page in the configured navigation has a companion.

## Configured navigation coverage

| English page | Chinese companion |
| --- | --- |
| [Home](index.md) | [首页](https://runchengxie.github.io/money-trees/zh-CN/) |
| [Public factor evidence](public-factor-evidence.md) | [公开因子证据](https://runchengxie.github.io/money-trees/zh-CN/public-factor-evidence/) |
| [Publication audit](publication-audit.md) | [发布审计](https://runchengxie.github.io/money-trees/zh-CN/publication-audit/) |
| [Research methodology](research-methodology.md) | [研究方法](https://runchengxie.github.io/money-trees/zh-CN/research-methodology/) |
| [Factor catalog](factor-catalog.md) | [因子目录](https://runchengxie.github.io/money-trees/zh-CN/factor-catalog/) |
| [Factor families](factor-families.md) | [因子族](https://runchengxie.github.io/money-trees/zh-CN/factor-families/) |
| [Data contract](data-contract.md) | [数据契约](https://runchengxie.github.io/money-trees/zh-CN/data-contract/) |
| [Architecture](architecture.md) | [架构](https://runchengxie.github.io/money-trees/zh-CN/architecture/) |
| [CLI reference](cli-reference.md) | [CLI 参考](https://runchengxie.github.io/money-trees/zh-CN/cli-reference/) |
| [Runbook](runbook.md) | [运维手册](https://runchengxie.github.io/money-trees/zh-CN/runbook/) |
| [Data input migration](data-platform-migration.md) | [数据入口迁移](https://runchengxie.github.io/money-trees/zh-CN/data-platform-migration/) |
| [Data snapshots](data-snapshot.md) | [数据快照](https://runchengxie.github.io/money-trees/zh-CN/data-snapshot/) |
| [Data release assets](data-release.md) | [数据发布资产](https://runchengxie.github.io/money-trees/zh-CN/data-release/) |
| [Data status checks](data-status.md) | [数据状态检查](https://runchengxie.github.io/money-trees/zh-CN/data-status/) |
| [Classic Alpha Python](classic-alphas-python.md) | [经典 Alpha Python](https://runchengxie.github.io/money-trees/zh-CN/classic-alphas-python/) |
| [Factor mining](factor-mining.md) | [因子挖掘](https://runchengxie.github.io/money-trees/zh-CN/factor-mining/) |
| [Smoke test](smoke-test.md) | [冒烟测试](https://runchengxie.github.io/money-trees/zh-CN/smoke-test/) |
| [Configuration](configuration.md) | [配置说明](https://runchengxie.github.io/money-trees/zh-CN/configuration/) |
| [Cookbook](cookbook.md) | [常见工作流](https://runchengxie.github.io/money-trees/zh-CN/cookbook/) |
| [Backtest outputs](outputs.md) | [回测产物](https://runchengxie.github.io/money-trees/zh-CN/outputs/) |
| [Testing](testing.md) | [测试说明](https://runchengxie.github.io/money-trees/zh-CN/testing/) |
| [DolphinDB Alpha generation](generate-alpha101-191-with-dolphindb.md) | [使用 DolphinDB 生成 Alpha101/191](https://runchengxie.github.io/money-trees/zh-CN/generate-alpha101-191-with-dolphindb/) |
| [Maintenance tasks](maintenance.md) | [维护待办](https://runchengxie.github.io/money-trees/zh-CN/maintenance/) |
| [Documentation language status](language-migration-status.md) | [文档语言状态](https://runchengxie.github.io/money-trees/zh-CN/language-migration-status/) |

The theme uses English on root pages and Chinese on `/zh-CN/` pages. Light and dark palettes follow `prefers-color-scheme`, with manual controls. Language selection changes documentation presentation only; it does not change project behavior or machine-readable contracts.

## Remaining scope

All 13 previously Chinese-only README-linked public guides now have an English canonical page and a Chinese companion. The two Markdown files under `docs/superpowers/` are internal plans/specifications and are excluded from the public MkDocs build.

When a page is promoted into navigation, verify its claims against the current implementation and tests, add its Chinese companion if needed, and place each page in its corresponding language navigation.
