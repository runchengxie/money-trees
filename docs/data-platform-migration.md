# 数据入口迁移

## 当前主路径

`money-trees` 不再把数据下载作为长期职责。正式研究应使用 `marketdata` 命令和 [`quant-market-data-platform`](https://github.com/runchengxie/quant-market-data-platform) 发布的、已经标准化、经过质量检查并带版本信息的数据资产，再交给 Money Trees 做因子计算和研究证据生产。

推荐链路：

```text
quant-market-data-platform
  接入 TuShare / 其他来源
  → 原始缓存、标准化、质量治理、版本和发布
        ↓ published parquet / data asset
money-trees
  读取 date,ticker 面板
  → 生成 Alpha 因子
  → 计算 IC / RankIC / 分组收益
  → 导出公开证据快照
```

## 兼容入口

`moneytrees-tushare` 以及 `moneytree-tushare` 仍暂时保留，用于复现旧 notebook 和迁移历史工作流，但它们是 deprecated 兼容路径，不是新的生产数据入口。它们会继续要求 TuShare 凭证、维护本地原始缓存，并承担与数据平台重复的标准化职责。

新研究不要再把 token、TuShare 原始缓存或 `manifest.sqlite` 放进 Money Trees 运行目录。优先使用数据平台发布的 parquet 或其他带版本的数据资产，然后通过 `--data`/面板输入交给回测或因子 CLI。

## 后续删除条件

只有在以下条件满足后，才删除兼容入口和相关测试：

1. 依赖 `moneytrees-tushare` 的旧 notebook 已完成迁移；
2. 数据平台已经提供当前 A 股面板所需的全部字段和版本契约；
3. Money Trees 的 CI 不再需要 TuShare extra；
4. 发布说明提供至少一个完整的迁移示例。
