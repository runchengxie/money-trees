# 公开因子证据

[English page](https://runchengxie.github.io/money-trees/public-factor-evidence/)

## 公开快照的定位

`moneytrees-factor-evidence` 从一个已经准备好的 `date, ticker` 面板生成聚合的 Alpha 研究证据。它用于检查因子是否形成稳定、可解释的研究信号，不替代完整策略回测，也不承诺未来收益。

快照包含：

- 因子名称和因子族；
- 样本区间、交易日数、观测数和覆盖率；
- IC、RankIC、IR 和正值比例；
- 分组平均收益及有效期间数；
- 数据版本、代码版本、计算配置和公开限制。

快照不包含逐股票因子值、股票代码、组合权重、原始数据路径、凭证或私有模型参数。

Schema 1.1 增加 `annual_slices`、`regime_slices` 和因子级 `uncertainty`；快照还会记录
`temporal_validation`、全局不确定性信息和 `multiple_testing`。统一的 `factor_evidence.v1`
包装器仍可读取 schema 1.0 快照。

年度切片按自然年汇总每日截面指标。`valid_dates` 统计 RankIC 有限的日期；年度分组收益先计算
每日组收益，再对有效日期求均值，并报告有效期数。这些是描述性子区间统计，不是相互独立的样本，
也不是留出验证区间。

只有因子仓库基础面板含有每日已实现基准收益、且每个日期只有一致的基准值时才发布市场状态切片。
规则使用信号日前严格结束的 252 个交易日基准复合收益：正值为 `bull`，否则为 `bear`；完整窗口
形成前的日期没有状态标签。不能把前瞻目标列当作基准收益。缺少基准数据或日期不重叠时，状态为
`not_provided` 并附原因；年度切片仍可用。

## 不确定性与多重检验

只有在已知前瞻目标构造时才传入 `--holding-period-days`：

```bash
uv run moneytrees-factor-evidence \
  --factor-store /data/moneytree-factor-store/manifest.json \
  --factors all \
  --holding-period-days 1 \
  --benchmark-return-column benchmark_daily_return \
  --benchmark-name "CSI 300" \
  --code-revision "$(git rev-parse HEAD)" \
  --output /tmp/alpha810-snapshot.json
```

传入 `--code-revision` 可在公开快照中记录源代码提交号。若同时指定 `--evidence-v1-output`，同一提交号也会写入统一证据文件的来源信息。

平均 RankIC 的不确定性采用 Newey–West HAC、Bartlett 权重和 `holding_period_days - 1` 阶滞后，
使用双侧标准正态参考分布和 95% 置信区间。缺失 RankIC 日期保留在每日序列中的原位置；不会把它
们视为零值，也不会把相隔多日的数据当作相邻观测。该结果描述每日截面 RankIC 均值的不确定性，
不代表组合收益的不确定性。

原始 p 值以 Benjamini–Yekutieli（BY）作为主要错误发现校正；Benjamini–Hochberg（BH）作为明确
标记的敏感性结果。校正分母是完整声明的因子族；数据不足的因子仍计入族规模，但不分配 q 值。
持有期缺失时，推断字段标记为 `not_provided`。原始 p 值和校正 q 值都不能证明可交易性或未来收益。

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
  --code-revision "$(git rev-parse HEAD)" \
  --output /tmp/alpha810-2016-2025.json \
  --quality-output /tmp/alpha810-2016-2025-quality.json
```

该模式只把当前读取的 Parquet 成员复制到临时文件供引擎读取，不会解压整个归档，也不会把归档路径写进公开快照。归档必须是未压缩 tar，并且其中的 `manifest.json`、基础面板和四个因子族必须属于同一版本。

## 下游边界

- `quant-platform` 消费研究层输出，负责策略无关的组合、风险、回测和执行模拟。
- `quant-backtest-runtime` 负责正式任务的提交、排队、worker、状态和结果归档。
- 模型训练、特征选择和策略晋升规则属于私有研究层。
- GitHub Pages 只展示由本工具导出的静态、脱敏聚合快照。
