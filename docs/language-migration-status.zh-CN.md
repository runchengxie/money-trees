# 文档语言状态

[English](https://runchengxie.github.io/money-trees/language-migration-status/)

MkDocs 站点默认使用英文，英文页保留原有根目录 URL，中文页使用 `/zh-CN/` 路径和相同页面名。每种语言只显示对应的导航；语言切换会打开另一种语言的对应页面。当前搜索索引包含两种语言，搜索结果可能跨语言。旧的 `*.zh-CN/` 链接会重定向到新中文路径。当前导航里的每页都有对应语言版本。

## 当前导航覆盖

| English page | 中文 companion |
| --- | --- |
| [Home](https://runchengxie.github.io/money-trees/) | [首页](https://runchengxie.github.io/money-trees/zh-CN/) |
| [Public factor evidence](https://runchengxie.github.io/money-trees/public-factor-evidence/) | [公开因子证据](https://runchengxie.github.io/money-trees/zh-CN/public-factor-evidence/) |
| [Publication audit](https://runchengxie.github.io/money-trees/publication-audit/) | [发布审计](https://runchengxie.github.io/money-trees/zh-CN/publication-audit/) |
| [Research methodology](https://runchengxie.github.io/money-trees/research-methodology/) | [研究方法](https://runchengxie.github.io/money-trees/zh-CN/research-methodology/) |
| [Factor catalog](https://runchengxie.github.io/money-trees/factor-catalog/) | [因子目录](https://runchengxie.github.io/money-trees/zh-CN/factor-catalog/) |
| [Factor families](https://runchengxie.github.io/money-trees/factor-families/) | [因子族](https://runchengxie.github.io/money-trees/zh-CN/factor-families/) |
| [Data contract](https://runchengxie.github.io/money-trees/data-contract/) | [数据契约](https://runchengxie.github.io/money-trees/zh-CN/data-contract/) |
| [Architecture](https://runchengxie.github.io/money-trees/architecture/) | [架构](https://runchengxie.github.io/money-trees/zh-CN/architecture/) |
| [CLI reference](https://runchengxie.github.io/money-trees/cli-reference/) | [CLI 参考](https://runchengxie.github.io/money-trees/zh-CN/cli-reference/) |
| [Runbook](https://runchengxie.github.io/money-trees/runbook/) | [运维手册](https://runchengxie.github.io/money-trees/zh-CN/runbook/) |
| [Data input migration](https://runchengxie.github.io/money-trees/data-platform-migration/) | [数据入口迁移](https://runchengxie.github.io/money-trees/zh-CN/data-platform-migration/) |
| [Data snapshots](https://runchengxie.github.io/money-trees/data-snapshot/) | [数据快照](https://runchengxie.github.io/money-trees/zh-CN/data-snapshot/) |
| [Data release assets](https://runchengxie.github.io/money-trees/data-release/) | [数据发布资产](https://runchengxie.github.io/money-trees/zh-CN/data-release/) |
| [Data status checks](https://runchengxie.github.io/money-trees/data-status/) | [数据状态检查](https://runchengxie.github.io/money-trees/zh-CN/data-status/) |
| [Classic Alpha Python](https://runchengxie.github.io/money-trees/classic-alphas-python/) | [经典 Alpha Python](https://runchengxie.github.io/money-trees/zh-CN/classic-alphas-python/) |
| [Factor mining](https://runchengxie.github.io/money-trees/factor-mining/) | [因子挖掘](https://runchengxie.github.io/money-trees/zh-CN/factor-mining/) |
| [Smoke test](https://runchengxie.github.io/money-trees/smoke-test/) | [冒烟测试](https://runchengxie.github.io/money-trees/zh-CN/smoke-test/) |
| [Configuration](https://runchengxie.github.io/money-trees/configuration/) | [配置说明](https://runchengxie.github.io/money-trees/zh-CN/configuration/) |
| [Cookbook](https://runchengxie.github.io/money-trees/cookbook/) | [常见工作流](https://runchengxie.github.io/money-trees/zh-CN/cookbook/) |
| [Backtest outputs](https://runchengxie.github.io/money-trees/outputs/) | [回测产物](https://runchengxie.github.io/money-trees/zh-CN/outputs/) |
| [Testing](https://runchengxie.github.io/money-trees/testing/) | [测试说明](https://runchengxie.github.io/money-trees/zh-CN/testing/) |
| [DolphinDB Alpha generation](https://runchengxie.github.io/money-trees/generate-alpha101-191-with-dolphindb/) | [使用 DolphinDB 生成 Alpha101/191](https://runchengxie.github.io/money-trees/zh-CN/generate-alpha101-191-with-dolphindb/) |
| [Maintenance tasks](https://runchengxie.github.io/money-trees/maintenance/) | [维护待办](https://runchengxie.github.io/money-trees/zh-CN/maintenance/) |
| [Documentation language status](https://runchengxie.github.io/money-trees/language-migration-status/) | [文档语言状态](https://runchengxie.github.io/money-trees/zh-CN/language-migration-status/) |

英文根页面使用英文主题，`/zh-CN/` 页面使用中文主题。页面配色会跟随系统的 `prefers-color-scheme`，并提供手动切换明暗主题的控件。语言只影响文档展示，不改变项目行为或机器可读契约。

## 后续范围

本清单建立后迁移的 13 篇指南此前由 README 链接，但只有中文版本。现在它们已有英文主版本、中文 companion，并加入两种语言的导航。

README 链接的 13 篇原本只有中文的公开指南，现在都有英文主版本、中文 companion，并进入各自语言的导航。`docs/superpowers/` 下的两篇 Markdown 是内部计划和规格，不属于公开站点，已从 MkDocs 构建中排除。

新增导航页面时，应先根据当前实现和测试核实内容，再按读者需求补充中文 companion，将两种语言页面放入各自的导航。
