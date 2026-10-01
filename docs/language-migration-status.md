# Documentation language status

[简体中文](language-migration-status.zh-CN.md)

The MkDocs site defaults to English and publishes English and Simplified Chinese as separate routes. Every page in the configured navigation has a reciprocal link to its companion. The navigation exposes both language groups.

## Configured navigation coverage

| English page | Chinese companion |
| --- | --- |
| [Home](index.md) | [首页](index.zh-CN.md) |
| [Public factor evidence](public-factor-evidence.md) | [公开因子证据](public-factor-evidence.zh-CN.md) |
| [Publication audit](publication-audit.md) | [发布审计](publication-audit.zh-CN.md) |
| [Research methodology](research-methodology.md) | [研究方法](research-methodology.zh-CN.md) |
| [Factor catalog](factor-catalog.md) | [因子目录](factor-catalog.zh-CN.md) |
| [Factor families](factor-families.md) | [因子族](factor-families.zh-CN.md) |
| [Data contract](data-contract.md) | [数据契约](data-contract.zh-CN.md) |
| [Architecture](architecture.md) | [架构](architecture.zh-CN.md) |
| [CLI reference](cli-reference.md) | [CLI 参考](cli-reference.zh-CN.md) |
| [Runbook](runbook.md) | [运维手册](runbook.zh-CN.md) |
| [Data input migration](data-platform-migration.md) | [数据入口迁移](data-platform-migration.zh-CN.md) |
| [Data snapshots](data-snapshot.md) | [数据快照](data-snapshot.zh-CN.md) |
| [Data release assets](data-release.md) | [数据发布资产](data-release.zh-CN.md) |
| [Data status checks](data-status.md) | [数据状态检查](data-status.zh-CN.md) |
| [Classic Alpha Python](classic-alphas-python.md) | [经典 Alpha Python](classic-alphas-python.zh-CN.md) |
| [Factor mining](factor-mining.md) | [因子挖掘](factor-mining.zh-CN.md) |
| [Smoke test](smoke-test.md) | [冒烟测试](smoke-test.zh-CN.md) |
| [Configuration](configuration.md) | [配置说明](configuration.zh-CN.md) |
| [Cookbook](cookbook.md) | [常见工作流](cookbook.zh-CN.md) |
| [Backtest outputs](outputs.md) | [回测产物](outputs.zh-CN.md) |
| [Testing](testing.md) | [测试说明](testing.zh-CN.md) |
| [DolphinDB Alpha generation](generate-alpha101-191-with-dolphindb.md) | [使用 DolphinDB 生成 Alpha101/191](generate-alpha101-191-with-dolphindb.zh-CN.md) |
| [Maintenance tasks](maintenance.md) | [维护待办](maintenance.zh-CN.md) |
| [Documentation language status](language-migration-status.md) | [文档语言状态](language-migration-status.zh-CN.md) |

The `theme.language` setting is `en`. Light and dark palettes follow `prefers-color-scheme`, and the theme provides manual light/dark controls. Language selection changes documentation presentation only; it does not change project behavior or machine-readable contracts.

## Remaining scope

The 13 guides added since this inventory was created were previously linked from the READMEs but existed only in Chinese. They now have English canonical pages, Chinese companions, and entries in both navigation groups.

All 13 previously Chinese-only README-linked public guides now have an English canonical page, a Chinese companion, and entries in both navigation groups. The two Markdown files under `docs/superpowers/` are internal plans/specifications and are not public README entry points. MkDocs still builds them, but they do not belong in public navigation.

When a page is promoted into the navigation, verify its claims against the current implementation and tests, add its Chinese companion, provide reciprocal links, and add both versions to the corresponding language navigation groups.
