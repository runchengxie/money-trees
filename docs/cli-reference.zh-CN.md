# CLI 参考

[English page](https://runchengxie.github.io/money-trees/cli-reference/)

本文汇总 Money Trees 当前 console scripts 和高风险参数。示例优先使用 `moneytrees*` 命令。`moneytree*` 同名别名仍保留，用于兼容旧脚本。数据下载不再是长期主路径；`moneytrees-tushare` 仅用于兼容，正式数据生产请使用 `quant-market-data-platform`。

## 命令和别名

| 推荐命令 | 兼容别名 | 用途 |
| --- | --- | --- |
| `moneytrees` | `moneytree` | 按配置运行回测。 |
| `moneytrees-tushare` | `moneytree-tushare` | 拉取 TuShare A 股日频数据，生成标准 `date, ticker` 面板。 |
| `moneytrees-factor-store` | `moneytree-factor-store` | 从基础面板生成本地 Alpha158/360 因子仓库。 |
| `moneytrees-dolphindb-alphas` | `moneytree-dolphindb-alphas` | 通过 DolphinDB 外部生成 Alpha101/191，写入因子仓库或兼容宽面板。 |
| `moneytrees-alpha101-191-python` | `moneytree-alpha101-191-python` | 用纯 Python（横截面语义）本地生成 Alpha101/191，写入因子仓库或兼容宽面板。 |
| `moneytrees-factor-mining` | `moneytree-factor-mining` | 用遗传算法在已有 Alpha 因子上挖掘新因子，输出训练适应度和留出 IC/ICIR/分位收益。 |
| `moneytrees-data-status` | `moneytree-data-status` | 只读检查原始缓存、基础面板、因子仓库和回测产物。 |
| `moneytrees-data-snapshot` | `moneytree-data-snapshot` | 生成基础面板、原始缓存和因子仓库的轻量元数据快照。 |
| `moneytrees-data-release` | `moneytree-data-release` | 生成 GitHub Releases 友好的数据发布资产并可选上传。 |
| `moneytrees-parquet-rewrite` | `moneytree-parquet-rewrite` | 重写 parquet 或迁移可信 pickle。 |
| `moneytrees-factor-evidence` | `moneytree-factor-evidence` | 生成仅含聚合信息的公开 Alpha 证据快照。 |

## `moneytrees`

| 参数 | 说明 |
| --- | --- |
| `--config` | 可重复传入配置文件。后传入的配置覆盖先传入的配置。 |
| `--data` | 覆盖配置中的数据入口，可指向标准面板或因子仓库 `manifest.json`。 |
| `--output-dir` | 覆盖回测产物输出目录。 |
| `--set` | 可重复传入 `dotted.path=value` 覆盖项。 |

## `moneytrees-tushare`（deprecated 兼容入口）

新研究应从 `quant-market-data-platform` 读取已发布面板；本命令只用于旧 notebook 迁移和历史复现。

| 参数 | 说明 |
| --- | --- |
| `--start-date`, `--end-date` | 拉取日期范围，支持 `YYYYMMDD` 或 `YYYY-MM-DD`。 |
| `--output` | 输出标准面板 parquet。 |
| `--benchmark` | 基准指数代码，默认 `000300.SH`。 |
| `--tickers` | 逗号分隔的股票代码。为空时使用 TuShare 返回的全部日频股票。 |
| `--factor-family` | 可重复传入 `alpha158` 或 `alpha360`，在输出面板中追加本地因子。 |
| `--cache-dir` | 原始缓存目录，按接口和交易日分区保存。 |
| `--cache-compression`, `--cache-compression-level`, `--cache-row-group-size` | 原始缓存 parquet 写入参数。 |
| `--refresh-cache` | 忽略已有原始缓存并重写。 |
| `--refresh-recent-days` | 缓存模式下强制刷新最近 N 个交易日。 |
| `--proxy-mode`, `--proxy-url`, `--no-fallback-direct` | TuShare 代理控制。`direct` 忽略 shell proxy 环境变量，`env` 使用环境变量，`proxy` 使用 `--proxy-url`。 |
| `--request-interval-seconds` | 真实 TuShare API 请求之间的最小间隔。缓存命中不等待。 |
| `--rate-limit-retries`, `--rate-limit-wait-seconds` | TuShare 限流错误后的重试次数和等待秒数。 |
| `--sanity-check` | 标准化后数据质量检查模式：`off`、`warn` 或 `error`。 |
| `--complete-calendar` | 重建交易日 x 股票代码完整网格，并把缺价行标记为停牌。 |
| `--raw-features`, `--factor-dtype` | 控制本地 Alpha158/360 使用未复权字段以及因子列 dtype。 |
| `--skip-daily-basic`, `--skip-adj-factor`, `--skip-limits`, `--skip-suspend`, `--skip-stock-basic` | 跳过指定 TuShare 接口。 |
| `--compression`, `--compression-level`, `--row-group-size` | 输出标准面板 parquet 写入参数。 |
| `--progress`, `--progress-every` | 输出拉取和因子生成进度。 |

## `moneytrees-factor-store`

| 参数 | 说明 |
| --- | --- |
| `--input` | 基础面板 parquet 或可信 pickle。 |
| `--output-dir` | 因子仓库目录。 |
| `--factor-family` | 可重复传入 `alpha158` 或 `alpha360`。 |
| `--raw-features` | 本地因子使用未复权 OHLCV/VWAP 字段。 |
| `--factor-dtype` | 因子列 dtype：`float32` 或 `float64`。 |
| `--chunk-trade-dates` | 每个分片包含的目标交易日数量。 |
| `--compression`, `--compression-level`, `--row-group-size` | 分片 parquet 写入参数。 |
| `--overwrite` | 已存在同名因子族时强制重算。 |
| `--progress` | 输出分片生成进度。 |

## `moneytrees-dolphindb-alphas`

| 参数 | 说明 |
| --- | --- |
| `--input` | Money Trees 标准面板 parquet 或可信 pickle。 |
| `--output` | 兼容宽面板输出路径。 |
| `--manifest-output` | 兼容宽面板路径的元数据清单输出。默认写到 `<output>.factor_manifest.json`。 |
| `--factor-store-output` | Alpha101/191 因子仓库输出目录。 |
| `--no-wide-output` | 只写入因子仓库，不生成兼容宽面板。 |
| `--host`, `--port`, `--user`, `--password` | DolphinDB 连接参数。密码默认读取 `DOLPHINDB_PASSWORD`，为空时使用本地默认值。 |
| `--family`, `--alpha101`, `--alpha191` | 选择要生成的外部因子族。 |
| `--alpha101-function`, `--alpha191-function` | DolphinDB 包装函数名。 |
| `--wq101-module-version`, `--gtja191-module-version`, `--moneytree-alpha-module-version` | 写入元数据清单的模块版本标签，不改变 DolphinDB `use` 模块名。 |
| `--raw-price-fields` | 输入同时存在复权和未复权价格时，使用未复权价格字段。 |
| `--factor-dtype` | 输出因子列 dtype：`float32` 或 `float64`。 |
| `--compression`, `--compression-level`, `--row-group-size` | 输出 parquet 写入参数。 |
| `--chunk-trade-dates` | 因子仓库分片交易日数量。在 `--no-wide-output` 路径中也控制 DolphinDB 计算窗口。 |
| `--overwrite` | 已存在同名外部因子族时强制重算。 |
| `--dolphindb-warmup-trade-dates` | 每个 streamed 计算窗口额外包含的历史交易日数量。 |
| `--stream-input` | parquet + `--no-wide-output` 路径的输入模式。`auto` 分窗口读取上传，`off` 使用旧的完整输入上传。 |
| `--skip-memory-check` | 跳过输入内存预检。只在明确接受 OOM 风险时使用。 |
| `--progress` | 输出分片写入进度。 |

## `moneytrees-alpha101-191-python`

| 参数 | 说明 |
| --- | --- |
| `--input` | Money Trees 标准面板 parquet 或可信 pickle。 |
| `--output` | 兼容宽面板输出路径。 |
| `--manifest-output` | 宽面板路径的元数据清单输出。默认写到 `<output>.factor_manifest.json`。 |
| `--factor-store-output` | Alpha101/191 因子仓库输出目录。 |
| `--no-wide-output` | 只写入因子仓库，不生成兼容宽面板。 |
| `--family`, `--alpha101`, `--alpha191` | 选择要本地生成的 Alpha 因子族。 |
| `--raw-price-fields` | 使用未复权价格字段。默认优先使用复权字段。 |
| `--factor-dtype` | 输出因子列 dtype：`float32` 或 `float64`。 |
| `--compression`, `--compression-level`, `--row-group-size` | 输出 parquet 写入参数。 |
| `--chunk-trade-dates` | 因子仓库分片交易日数量。 |
| `--overwrite` | 已存在同名外部因子族时强制重算。 |
| `--progress` | 输出逐因子计算和分片写入进度。 |

口径差异见 [classic-alphas-python.md](classic-alphas-python.md)。

## `moneytrees-factor-mining`

| 参数 | 说明 |
| --- | --- |
| `--data` | 标准面板 parquet/pickle 或因子仓库 `manifest.json`。 |
| `--factor-prefixes` | 可重复传入的因子列前缀，作为 GP 终端集合。 |
| `--factor-column` | 可重复传入的显式因子列名。 |
| `--start-date`, `--end-date` | 训练窗口。 |
| `--test-start-date`, `--test-end-date` | 留出验证窗口。 |
| `--future-return-period` | 未来收益周期（交易日），默认 5。 |
| `--pop-size`, `--max-gen`, `--max-depth` | 种群大小、最大进化代数、表达式树最大深度。 |
| `--seed` | 随机种子。 |
| `--complexity-penalty`, `--crossover-rate`, `--mutation-rate`, `--elitism-rate`, `--tournament-size` | GP 超参数。 |
| `--neutralize` | 验证时对市值中性化后再计算分位收益。 |
| `--output-dir` | 必填，写入 `mining_report.json` 和 `best_factor.txt`。 |

用法见 [factor-mining.md](factor-mining.md)。

## `moneytrees-data-status`

| 参数 | 说明 |
| --- | --- |
| `--panel` | 基础 `date, ticker` 面板 parquet 或可信 pickle。 |
| `--raw-cache` | TuShare 原始缓存目录或 `manifest.sqlite`。 |
| `--factor-store` | 因子仓库目录或 `manifest.json`。 |
| `--artifacts` | 回测产物目录。 |
| `--factor-family`, `--factor-families` | 只检查指定因子族，可重复或逗号分隔。 |
| `--skip-factor-quality` | 只检查因子仓库元数据清单和文件存在性，跳过因子值扫描。 |
| `--allow-factor-column` | 允许已知全空、高空值率或常数因子列。 |
| `--progress` | 输出因子仓库质量扫描进度。 |
| `--format` | 输出 `text` 或 `json`。 |
| `--mode` | 数据问题的退出码策略：`warn` 或 `error`。 |

`moneytrees-data-status` 是只读命令：不会刷新原始缓存、修复面板、重写因子仓库或改动回测产物。

## `moneytrees-data-snapshot`

| 参数 | 说明 |
| --- | --- |
| `--panel` | 必填，基础面板 parquet 或可信 pickle。 |
| `--output-dir` | 必填，快照元数据输出目录。 |
| `--raw-cache` | 可选，原始缓存目录或 `manifest.sqlite`。 |
| `--factor-store` | 可选，因子仓库目录或 `manifest.json`。 |
| `--raw-cache-compression` | `none` 或 `zstd`，默认 `none`。使用 Zstandard 前需运行 `uv sync --extra release`。 |
| `--raw-cache-compression-level` | Zstandard 压缩级别 1–22，默认 19；固定使用 27 位长距离窗口。 |
| `--label` | 可选的人类可读快照标签。 |
| `--note` | 可重复写入 `dataset_meta.json` 和快照 README 的说明。 |
| `--format` | 输出 `text` 或 `json`。 |

快照记录元数据和校验码，引用大型数据文件，不复制完整数据。

## `moneytrees-data-release`

| 参数 | 说明 |
| --- | --- |
| `--output-dir` | 必填，发布资产输出目录，支持 `/mnt/d/...` 和 `D:/...` 形式。 |
| `--panel` | 可选，基础面板 parquet 或可信 pickle。 |
| `--raw-cache` | 可选，原始缓存目录或 `manifest.sqlite`。 |
| `--factor-store` | 可选，因子仓库目录或 `manifest.json`。 |
| `--max-asset-size-mb` | 单个生成资产的大小上限，默认 1536 MiB。 |
| `--label` | 可选的人类可读发布标签。 |
| `--note` | 可重复写入 `manifest.json` 和 README 的说明。 |
| `--dry-run` | 只预览计划资产，不写文件，不上传。 |
| `--overwrite` | 允许替换 `--output-dir` 中已有的同名生成文件。 |
| `--no-resume` | 关闭可恢复输出复用，已有文件需要 `--overwrite`。 |
| `--progress` | 在 stderr 输出发布资产生成进度。 |
| `--skip-space-check` | 跳过目标文件系统剩余空间预检。 |
| `--github-repo` | GitHub 仓库，格式为 `OWNER/REPO`。 |
| `--github-tag` | GitHub release tag。 |
| `--upload` | 使用 GitHub CLI 上传生成资产。 |
| `--create-release` | 上传前先用 GitHub CLI 创建 release。 |
| `--release-title` | 创建 release 时使用的标题。 |
| `--clobber` | 上传时传给 GitHub CLI 的覆盖参数。 |
| `--format` | 输出 `text` 或 `json`。 |

目录型输入会生成 tar 分片。原始缓存分片可选用 Zstandard 压缩；因子仓库分片保持不压缩。单个超限文件会拆成 `.partNNNofMMM`。命令默认只生成本地资产，只有显式传入 `--upload` 才会联网调用 GitHub CLI。

## `moneytrees-parquet-rewrite`

| 参数 | 说明 |
| --- | --- |
| `--input` | 输入 parquet 或可信 pickle。 |
| `--output` | 输出 parquet。 |
| `--compression`, `--compression-level`, `--row-group-size` | 输出 parquet 写入参数。 |
| `--overwrite` | 允许覆盖已有输出。原地重写仍会被拒绝。 |
| `--no-verify` | 跳过写出后的行列和索引验证。 |

pickle 输入只适合可信历史数据迁移。日常研究路径优先使用 parquet。

## `moneytrees-factor-evidence`

本命令生成聚合研究证据，不代替完整策略回测。结果解释和发布边界见[公开因子证据](public-factor-evidence.md)。

| 参数 | 说明 |
| --- | --- |
| `--panel`、`--factor-store`、`--factor-store-archive` | 三种输入只能选一种：面板、分区因子仓库清单或不压缩的仓库归档。 |
| `--families` | 逗号分隔的仓库因子族，默认使用全部。 |
| `--date-start`、`--date-end` | 包含边界日期的仓库数据筛选。 |
| `--factors` | 必填，逗号分隔的因子名或每行一个因子名的文本文件；仓库输入只接受 `all` 或 `*`。 |
| `--return-column` | 未来收益列，默认 `next_period_return`。 |
| `--benchmark-return-column`、`--benchmark-name` | 市场状态分层所用的已实现日基准收益列和可读名称。 |
| `--regime-window` | 市场状态标签使用的此前交易日数，默认 252。 |
| `--holding-period-days` | 未来收益持有天数；输出推断性诊断前必须提供。 |
| `--data-version`、`--code-revision` | 写入快照的数据版本和代码修订号。 |
| `--output` | 必填，聚合快照 JSON 路径。 |
| `--quality-output` | 可选的聚合信号质量 JSON 路径。 |
| `--evidence-v1-output` | 可选的统一 `factor_evidence.v1` JSON 路径。 |
| `--group-count` | 收益分组数，默认 5。 |
| `--format` | CLI 输出为 `text` 或 `json`。 |
