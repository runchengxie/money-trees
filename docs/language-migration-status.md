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
| [Documentation language status](language-migration-status.md) | [文档语言状态](language-migration-status.zh-CN.md) |

The `theme.language` setting is `en`. Light and dark palettes follow `prefers-color-scheme`, and the theme provides manual light/dark controls. Language selection changes documentation presentation only; it does not change project behavior or machine-readable contracts.

## Remaining scope

This inventory covers the pages configured in `mkdocs.yml` navigation. Additional Markdown files exist under `docs/` outside that navigation and are not counted as localized public entry pages here. MkDocs reports unlisted pages during a strict build; review their intended publication and reader access before deciding whether to add them to navigation or translate them.

When a page is promoted into the navigation, verify its claims against the current implementation and tests, add its Chinese companion, provide reciprocal links, and add both versions to the corresponding language navigation groups.
