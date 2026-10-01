# 文档语言状态

[English](language-migration-status.md)

MkDocs 站点默认使用英文，英文和简体中文页面分别发布在独立 URL 中。当前导航里的每个页面都有对应语言版本和互相链接，导航也分别列出两种语言。

## 当前导航覆盖

| English page | 中文 companion |
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

`theme.language` 配置为 `en`。页面配色会跟随系统的 `prefers-color-scheme`，并提供手动切换明暗主题的控件。语言只影响文档展示，不改变项目行为或机器可读契约。

## 后续范围

本清单只统计 `mkdocs.yml` 导航中列出的页面。`docs/` 下还有其他未列入导航的 Markdown 文件，因此它们不计入当前公开入口的双语覆盖。严格构建会提示这些未列入导航的页面；决定是否加入导航或翻译前，应先确认它们是否需要公开以及读者如何访问。

新增导航页面时，应先根据当前实现和测试核实内容，再补充中文 companion、双向语言链接，并将两个版本都加入对应语言导航组。
