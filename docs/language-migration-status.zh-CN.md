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
| [Data input migration](data-platform-migration.md) | [数据入口迁移](data-platform-migration.zh-CN.md) |
| [Data snapshots](data-snapshot.md) | [数据快照](data-snapshot.zh-CN.md) |
| [Data release assets](data-release.md) | [数据发布资产](data-release.zh-CN.md) |
| [Documentation language status](language-migration-status.md) | [文档语言状态](language-migration-status.zh-CN.md) |

`theme.language` 配置为 `en`。页面配色会跟随系统的 `prefers-color-scheme`，并提供手动切换明暗主题的控件。语言只影响文档展示，不改变项目行为或机器可读契约。

## 后续范围

上面新增的三篇数据文档此前由 README 链接，但只有中文版本。现在它们已有英文主版本、中文 companion，并加入两种语言的导航。

## 尚待补充英文主版本的 README 文档

以下十篇由 README 链接的文档，其无后缀文件目前仍为中文，也还没有英文主版本：

- `classic-alphas-python.md`
- `configuration.md`
- `cookbook.md`
- `data-status.md`
- `factor-mining.md`
- `generate-alpha101-191-with-dolphindb.md`
- `maintenance.md`
- `outputs.md`
- `smoke-test.md`
- `testing.md`

在根据当前实现核实英文内容并配好中文页面前，这些文档暂不加入导航。`docs/superpowers/` 下的两篇 Markdown 是内部计划和规格，不属于 README 的公开入口。MkDocs 仍会构建未列入导航的 Markdown；严格构建会列出它们，但这不代表它们都应进入公开导航。

新增导航页面时，应先根据当前实现和测试核实内容，再补充中文 companion、双向语言链接，并将两个版本都加入对应语言导航组。
