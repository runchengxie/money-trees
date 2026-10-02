# 使用 DolphinDB 生成 Alpha101/191

[English page](https://runchengxie.github.io/money-trees/generate-alpha101-191-with-dolphindb/)

本文说明如何把 DolphinDB 作为 Alpha101/191 的外部因子生产器使用。Money Trees 仍然只消费离线生成结果，不在回测过程中实时调用 DolphinDB。推荐新路径是写入因子仓库。旧的宽 parquet 面板输出继续保留用于兼容。

## 当前边界

`docs/factor-catalog.csv` 覆盖 810 个因子列名：

| 因子族 | 数量 | 项目内计算状态 |
| --- | ---: | --- |
| Alpha101 | 101 | 本地 `build_alpha101_features` 生成，或 DolphinDB 外部生成后并入 |
| Alpha191 | 191 | 本地 `build_alpha191_features` 生成，或 DolphinDB 外部生成后并入 |
| Alpha158 | 158 | 本地 `build_alpha158_features` 生成 |
| Alpha360 | 360 | 本地 `build_alpha360_features` 生成 |

也就是说，810 个因子都有项目内计算路径：Alpha158/360 由 `qlib.py` 本地生成，Alpha101/191 由 `classic.py` 纯 Python 本地生成（横截面语义，见[纯 Python Alpha101/191](https://runchengxie.github.io/money-trees/zh-CN/classic-alphas-python/)），也可以继续走本文的 DolphinDB 外部生成契约。DolphinDB 路径的 rank/scale、缺失值、SMA/DECAYLINEAR 语义与本地路径可能不同，正式使用前建议小样本对拍。

推荐数据流：

```text
quant-market-data-platform 发布的版本化日频面板
-> DolphinDB 离线计算 Alpha101/191
-> 写入 data/factor_store/cn 的 alpha101 / alpha191 分族分片
-> moneytrees 使用因子仓库元数据清单正常回测
```

兼容数据流仍可用：

```text
标准日频面板
-> DolphinDB 离线计算 Alpha101/191
-> 输出带 alpha101_* / alpha191_* 的宽 parquet
-> moneytrees 使用该 parquet 正常回测
```

所有进入模型的特征仍受市场配置档中的 `feature_lag_periods` 约束。默认 `feature_lag_periods=1`。

## WSL 推荐环境

如果开发环境在 WSL，推荐：

```text
Windows Docker Desktop
-> WSL 2 backend
-> WSL 发行版内运行 docker CLI
-> DolphinDB 单节点容器
```

项目代码建议放在 WSL 文件系统内，例如 `~/code/money-trees`，不要放在 `/mnt/c/...` 下。

安装和检查顺序：

```powershell
wsl --version
wsl -l -v
```

确保开发发行版是 WSL 2。然后在 Docker Desktop 中启用：

```text
Settings -> General -> Use WSL 2 based engine
Settings -> Resources -> WSL Integration -> Enable integration with your distro
```

在 WSL 中检查：

```bash
docker version
docker ps
```

## DolphinDB 容器

仓库提供了 compose scaffold：

```bash
docker compose -f docker-compose.alpha.yml run --rm moneytrees \
  -lc 'moneytrees-dolphindb-alphas --help'
```

该 compose 文件把 `moneytrees` Python runner 和 `dolphindb` server 分成两个 service。Python runner 挂载 `data/`、`artifacts/` 和 `docker/dolphindb/modules/`。DolphinDB server 只挂载自己的 server data 子目录，避免覆盖镜像内置的 `/data/ddb/server/dolphindb` 启动程序。DolphinDB 镜像 tag、license 和模块来源仍需按你的实际环境固定。

在项目根目录创建本地挂载目录：

```bash
mkdir -p docker/dolphindb/modules docker/dolphindb/bootstrap
```

启动单节点容器，镜像版本请在本地固定成你实际验证过的版本：

```bash
docker run -itd \
  --name dolphindb-alpha \
  --hostname host1 \
  -p 8848:8848 \
  -v "$PWD/docker/dolphindb/modules:/data/ddb/server/modules" \
  -v "$PWD/data/ddb/server/data:/data/ddb/server/data" \
  dolphindb/dolphindb:<ddb-version> \
  sh
```

本地浏览器可访问：

```text
http://localhost:8848
```

默认登录通常是：

```text
admin / 123456
```

## DolphinDB 模块

把外部获取或本地维护的模块放到：

```text
docker/dolphindb/modules/
```

使用本仓库 `docker-compose.alpha.yml` 时，该目录会只读挂载到 DolphinDB server 的：

```text
/data/ddb/server/data/modules
```

如果你用下方手工 `docker run` 示例，请确保挂载目标是你所用 DolphinDB 镜像实际读取模块的 server modules 目录。

预期文件：

```text
wq101alpha.dos
prepare101.dos
gtja191Alpha.dos
gtja191Prepare.dos
moneytreeAlpha.dos
```

这些 `.dos` 文件按本地准备、不随仓库提交的方式维护，需要先按上面模块说明准备好再使用。`wq101alpha.dos` / `gtja191Alpha.dos` 是 DolphinDB 公式模块，`prepare101.dos` / `gtja191Prepare.dos` 是准备模块，`moneytreeAlpha.dos` 是 Money Trees 适配包装模块。生产使用前应确认模块来源、授权和版本，并在生成命令中记录 module version。`moneytreeAlpha.dos` 建议提供两个函数：

```text
calcMoneyTreeAlpha101(rawData, startTime, endTime)
calcMoneyTreeAlpha191(rawData, startTime, endTime)
```

返回宽表：

```text
tradetime, securityid, alpha101_001, ..., alpha101_101
tradetime, securityid, alpha191_001, ..., alpha191_191
```

Python 脚本只负责上传标准化输入、调用包装函数、下载结果、校验列，并写入因子仓库或兼容合并回宽面板。

补齐模块并重启 DolphinDB 后，可以先只验证模块加载：

```bash
uv run python -c 'import dolphindb as ddb; s=ddb.Session(); s.connect("127.0.0.1",8848,"admin","123456"); print(s.run("use wq101alpha; use prepare101; use gtja191Alpha; use gtja191Prepare; use moneytreeAlpha; 1"))'
```

返回 `1` 后再运行 `moneytrees-dolphindb-alphas`。CLI 也会在正式上传面板前做 preflight：如果缺少模块或 `moneytreeAlpha.dos` 中缺少 wrapper 函数，错误会直接指出缺少的模块或函数。`--wq101-module-version`、`--gtja191-module-version` 和 `--moneytree-alpha-module-version` 只记录元数据清单，不会改变 DolphinDB 的 `use` 模块名。

CLI 默认从 `DOLPHINDB_PASSWORD` 读取密码。环境变量未设置或为空时，回退到本地开发默认密码 `123456`。如果显式传 `--password`，该值必须非空。

## 字段映射

CLI 会把 Money Trees 面板映射成 DolphinDB 输入：

| DolphinDB 字段 | Money Trees 字段 |
| --- | --- |
| `tradetime` | `date` |
| `securityid` | `ticker` |
| `open` | 优先 `open_adj`，回退 `open` |
| `high` | 优先 `high_adj`，回退 `high` |
| `low` | 优先 `low_adj`，回退 `low` |
| `close` | 优先 `close_adj`，回退 `close` |
| `vwap` | 优先 `vwap_adj`，回退 `vwap` |
| `vol` | 优先 `volume`，回退 `vol * 100` |
| `cap` | 优先 `circ_mv`，回退 `total_mv`，仍缺失则记为空 |
| `indclass` | `industry`，缺失时填 `UNKNOWN` |
| `index_open` | `benchmark_open` |
| `index_close` | `benchmark_close` |

Alpha191 请求会要求 `benchmark_open` 和 `benchmark_close` 存在。Alpha101 中行业和市值相关因子依赖 `indclass` 和 `cap`。如果行业字段不是 point-in-time 行业分类，历史回测会有未来信息污染风险。

## 运行生成

新研究应优先使用 `quant-market-data-platform` 发布的版本化面板。下方 `moneytrees-tushare` 命令仅用于复现旧 notebook 和迁移历史工作流；数据职责边界见[数据入口迁移](https://runchengxie.github.io/money-trees/zh-CN/data-platform-migration/)。DolphinDB 生成器本身只读取现有面板，不负责获取原始数据。

DolphinDB Python client 不在核心依赖中。需要生成外部因子时，在当前环境安装 external-alpha 依赖：

```bash
uv sync --dev --extra external-alphas
```

如需复现旧工作流，可用保留的 TuShare 兼容入口生成基础或本地 Alpha158/360 面板：

```bash
uv run moneytrees-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha158_360.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

推荐直接写入因子仓库：

首次打通环境时，建议分阶段执行，先只保留 `--alpha101` 跑到临时输出目录，再只保留 `--alpha191` 跑到临时输出目录。两边都通过后，再同时带上 `--alpha101 --alpha191` 写入正式因子仓库。Alpha191 需要输入面板包含 `benchmark_open` 和 `benchmark_close`。

使用 `--no-wide-output` 写入因子仓库且输入是 parquet 时，CLI 默认使用 `--stream-input auto`：按 `--chunk-trade-dates` 划分目标交易日，每个计算窗口额外包含 `--dolphindb-warmup-trade-dates` 指定的历史交易日，随后只读取并上传该窗口、调用 DolphinDB、只下载目标交易日结果并立即写入分片。这个路径避免在 Python 或 DolphinDB client 中构造多年全市场的完整输入/输出宽表。重新生成已写入元数据清单的外部因子族时传 `--overwrite`。兼容宽 parquet 输出路径仍然需要一次性返回完整宽表。

内存边界：`--stream-input auto` 只支持 parquet + `--no-wide-output` 的因子仓库路径。宽表输出、pickle 输入或显式 `--stream-input off` 会走旧的完整输入上传路径。多年全市场输入可能 OOM，CLI 会在读取前做内存预检并给出错误。除非明确接受 OOM 风险，不要用 `--skip-memory-check` 绕过该保护。

Alpha101 单独验证时保留同一组连接和版本参数，只改输出目录并只传 `--alpha101`：

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn-alpha101-check \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

Alpha191 单独验证时只传 `--alpha191`：

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn-alpha191-check \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha191 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

最终写入正式因子仓库时仍建议按因子族分开运行。同时生成 `--alpha101 --alpha191` 只适合内存充足并且已经完成单因子族验证的环境：

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/panel/cn/cn_daily_raw.parquet \
  --factor-store-output data/factor_store/cn \
  --no-wide-output \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --factor-dtype float32 \
  --chunk-trade-dates 60 \
  --stream-input auto \
  --overwrite \
  --dolphindb-warmup-trade-dates 260 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

然后直接从因子仓库回测：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/factor_store/cn/manifest.json \
  --output-dir artifacts/xgb-alpha-all
```

旧路径仍可生成并合并 Alpha101/191 到宽面板：

```bash
uv run moneytrees-dolphindb-alphas \
  --input data/cn_daily_alpha158_360.parquet \
  --output data/cn_daily_alpha_all.parquet \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --alpha101 \
  --alpha191 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

`scripts/build_dolphindb_alphas.py` 仍保留为兼容 wrapper，新的正式入口是 `moneytrees-dolphindb-alphas`。

旧路径输出：

```text
data/cn_daily_alpha_all.parquet
data/cn_daily_alpha_all.parquet.factor_manifest.json
```

然后正常回测：

```bash
uv run moneytrees \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/xgb-alpha-all
```

## 元数据清单

每次成功生成都会写元数据清单，记录：

- 因子来源和家族。
- 输入/输出文件 hash。
- 输入/输出 schema 摘要。
- DolphinDB host、port、user、server version 和 Python client version。
- WQ101、GTJA191、`moneytreeAlpha` 模块版本标签。
- 价格、成交量、市值、行业和基准字段选择。
- fallback 字段和缺失可选字段。
- 列完整性和键匹配校验结果。

元数据清单不记录密码、token、`.env` 内容或 TuShare token。

## 校验规则

生成脚本会拒绝以下情况：

- 输入面板存在重复 `date, ticker`。
- 请求 Alpha101 但输出缺少 `alpha101_001...alpha101_101` 中任意列。
- 请求 Alpha191 但输出缺少 `alpha191_001...alpha191_191` 中任意列。
- 输出包含请求范围外的 `alpha101_` 或 `alpha191_` 列。
- DolphinDB 返回了不在输入面板内的 `date, ticker`。
- 输出与输入没有任何匹配键，或匹配键上所有请求因子值都是空。

这些校验用于保证外部因子生产遵守正式数据契约。

## 研究风险

- `rank`、`ts_rank`、`decay_linear`、`SMA` 等算子在不同实现中可能有口径差异。
- `vwap`、复权价格、市值和行业分类会显著影响因子值。
- Alpha101 行业相关因子需要 point-in-time 行业分类。
- Alpha191 依赖的基准开收盘字段需要与回测基准一致。
- 不建议混用多个 Alpha101/191 实现来源后直接比较结果。应先固定 DolphinDB 和模块版本。
