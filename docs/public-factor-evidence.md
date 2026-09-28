# 公开因子证据

## 公开快照的定位

`moneytrees-factor-evidence` 从一个已经准备好的 `date, ticker` 面板生成聚合的 Alpha 研究证据。它用于检查因子是否形成稳定、可解释的研究信号，不替代完整策略回测，也不承诺未来收益。

快照包含：

- 因子名称和因子族；
- 样本区间、交易日数、观测数和覆盖率；
- IC、RankIC、IR 和正值比例；
- 分组平均收益及有效期间数；
- 数据版本、代码版本、计算配置和公开限制。

快照不包含逐股票因子值、股票代码、组合权重、原始数据路径、凭证或私有模型参数。

## 本地生成

```bash
uv run moneytrees-factor-evidence \
  --panel /path/to/research-panel.parquet \
  --factors alpha101_001,alpha158_001 \
  --data-version cn-daily-2026-09 \
  --output /tmp/alpha810-snapshot.json
```

数据可以来自受控硬盘盒或私有研究环境。生成步骤只读取输入，输出目录应位于仓库外；提交前必须运行公开发布审计。

## 下游边界

- `quant-platform` 消费研究层输出，负责策略无关的组合、风险、回测和执行模拟。
- `quant-backtest-runtime` 负责正式任务的提交、排队、worker、状态和结果归档。
- 模型训练、特征选择和策略晋升规则属于私有研究层。
- GitHub Pages 只展示由本工具导出的静态、脱敏聚合快照。
