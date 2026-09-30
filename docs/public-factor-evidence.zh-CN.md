# 公开因子证据

[English page](public-factor-evidence.md)

## 公开快照的定位

`moneytrees-factor-evidence` 从一个已经准备好的 `date, ticker` 面板生成聚合的 Alpha 研究证据。它用于检查因子是否形成稳定、可解释的研究信号，不替代完整策略回测，也不承诺未来收益。

快照包含：

- 因子名称和因子族；
- 样本区间、交易日数、观测数和覆盖率；
- IC、RankIC、IR 和正值比例；
- 分组平均收益及有效期间数；
- 数据版本、代码版本、计算配置和公开限制。

快照不包含逐股票因子值、股票代码、组合权重、原始数据路径、凭证或私有模型参数。

## 信号质量检查

可在生成快照时同时生成聚合质量报告：

```bash
uv run moneytrees-factor-evidence \
  --factor-store /data/moneytree-factor-store/manifest.json \
  --factors all \
  --output /tmp/alpha810-snapshot.json \
  --quality-output /tmp/alpha810-signal-quality.json
```

如需交给正式回测或 Observatory 的统一证据契约，可额外指定：

```bash
  --evidence-v1-output /tmp/factor-evidence.v1.json
```

`factor_evidence.v1` 将预测性结果、不确定性、风险、残差、时间验证和来源
信息放在同一个聚合 artifact 中；未提供的诊断会明确标记为 `not_provided`。

报告检查因子数量、覆盖率和 RankIC 可用性。`pass` 表示没有发现门禁问题，`warn` 表示需要人工复核，`fail` 表示没有可用因子。它是数据与研究质量门禁，不是收益承诺。

## 本地生成

```bash
uv run moneytrees-factor-evidence \
  --panel /path/to/research-panel.parquet \
  --factors alpha101_001,alpha158_001 \
  --data-version cn-daily-2026-09 \
  --output /tmp/alpha810-snapshot.json
```

数据可以来自受控硬盘盒或私有研究环境。生成步骤只读取输入，输出目录应位于仓库外；提交前必须运行公开发布审计。

对于 Money Trees 因子仓库，推荐直接读取 `manifest.json`。命令会按分区读取，不会把完整的 810 因子宽表一次性加载到内存：

```bash
uv run moneytrees-factor-evidence \
  --factor-store /data/moneytree-factor-store/manifest.json \
  --families alpha101,alpha191,alpha158,alpha360 \
  --factors all \
  --date-start 2016-01-01 \
  --date-end 2025-12-31 \
  --data-version cn-factor-store-2016-2025 \
  --output /tmp/alpha810-snapshot.json
```

`--factor-store` 只消费因子仓库中的已发布基础面板和因子分区；硬盘盒路径、原始数据和中间文件不会写入公开快照。生产发布前应确认因子仓库的 `manifest.json`、基础面板和各因子分区来自同一版本。

如果因子仓库仍在未解压的硬盘归档中，可以直接指定未压缩的 tar 文件：

```bash
uv run moneytrees-factor-evidence \
  --factor-store-archive /data/money-tree_20260502_103017.tar \
  --families alpha101,alpha191,alpha158,alpha360 \
  --factors all \
  --date-start 2016-01-01 \
  --date-end 2025-12-31 \
  --data-version cn-factor-store-2016-2025-archive \
  --output /tmp/alpha810-2016-2025.json \
  --quality-output /tmp/alpha810-2016-2025-quality.json
```

该模式只把当前读取的 Parquet 成员复制到临时文件供引擎读取，不会解压整个归档，也不会把归档路径写进公开快照。归档必须是未压缩 tar，并且其中的 `manifest.json`、基础面板和四个因子族必须属于同一版本。

## 下游边界

- `quant-platform` 消费研究层输出，负责策略无关的组合、风险、回测和执行模拟。
- `quant-backtest-runtime` 负责正式任务的提交、排队、worker、状态和结果归档。
- 模型训练、特征选择和策略晋升规则属于私有研究层。
- GitHub Pages 只展示由本工具导出的静态、脱敏聚合快照。
