# DolphinDB Alpha101/191 外部因子生产

本文说明如何把 DolphinDB 作为 Alpha101/191 的外部因子生产器使用。`money-tree` 仍然只消费最终 parquet 面板，不在回测过程中实时调用 DolphinDB。

## 当前边界

`docs/factor_catalog.csv` 覆盖 810 个因子列名：

| 因子族 | 数量 | 项目内计算状态 |
| --- | ---: | --- |
| Alpha101 | 101 | 外部生成后并入面板 |
| Alpha191 | 191 | 外部生成后并入面板 |
| Alpha158 | 158 | 本地 `build_alpha158_features` 生成 |
| Alpha360 | 360 | 本地 `build_alpha360_features` 生成 |

也就是说，当前本地可计算特征是 Alpha158/360 共 518 个。Alpha101/191 共 292 个列是外部生成契约，不是本仓库内置公式实现。

推荐数据流：

```text
TuShare / 标准日频面板
-> DolphinDB 离线计算 Alpha101/191
-> 输出带 alpha101_* / alpha191_* 的 parquet
-> moneytree 使用该 parquet 正常回测
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

项目代码建议放在 WSL 文件系统内，例如 `~/code/money-tree`，不要放在 `/mnt/c/...` 下。

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

在项目根目录创建本地挂载目录：

```bash
mkdir -p infra/dolphindb/modules infra/dolphindb/data infra/dolphindb/logs
```

启动单节点容器，镜像版本请在本地固定成你实际验证过的版本：

```bash
docker run -itd \
  --name dolphindb-alpha \
  --hostname host1 \
  -p 8848:8848 \
  -v "$PWD/infra/dolphindb/modules:/data/ddb/server/modules" \
  -v "$PWD/infra/dolphindb/data:/data/ddb/server/data" \
  -v "$PWD/infra/dolphindb/logs:/data/ddb/server/log" \
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
infra/dolphindb/modules/
```

预期文件：

```text
wq101alpha.dos
prepare101.dos
gtja191Alpha.dos
gtja191Prepare.dos
moneytreeAlpha.dos
```

这些 `.dos` 文件不提交到仓库。`moneytreeAlpha.dos` 是本地适配包装模块，建议提供两个函数：

```text
calcMoneyTreeAlpha101(rawData, startTime, endTime)
calcMoneyTreeAlpha191(rawData, startTime, endTime)
```

返回宽表：

```text
tradetime, securityid, alpha101_001, ..., alpha101_101
tradetime, securityid, alpha191_001, ..., alpha191_191
```

Python 脚本只负责上传标准化输入、调用包装函数、下载结果、校验列并合并回面板。

## 字段映射

脚本会把 `money-tree` 面板映射成 DolphinDB 输入：

| DolphinDB 字段 | money-tree 字段 |
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

Alpha191 请求会要求 `benchmark_open` 和 `benchmark_close` 存在。Alpha101 中行业和市值相关因子依赖 `indclass` 和 `cap`；如果行业字段不是 point-in-time 行业分类，历史回测会有未来信息污染风险。

## 运行生成

DolphinDB Python client 不在核心依赖中。需要生成外部因子时，在当前环境安装：

```bash
uv pip install dolphindb
```

先生成基础或本地 Alpha158/360 面板：

```bash
uv run moneytree-tushare \
  --start-date 20180101 \
  --end-date 20241231 \
  --output data/cn_daily_alpha158_360.parquet \
  --cache-dir data/raw/tushare \
  --refresh-recent-days 20 \
  --benchmark 000300.SH \
  --factor-family alpha158 \
  --factor-family alpha360
```

再生成并合并 Alpha101/191：

```bash
uv run python scripts/build_dolphindb_alphas.py \
  --input data/cn_daily_alpha158_360.parquet \
  --output data/cn_daily_alpha_all.parquet \
  --host 127.0.0.1 \
  --port 8848 \
  --user admin \
  --password 123456 \
  --alpha101 \
  --alpha191 \
  --wq101-module-version <your-wq101-version> \
  --gtja191-module-version <your-gtja191-version> \
  --moneytree-alpha-module-version <your-wrapper-version>
```

输出：

```text
data/cn_daily_alpha_all.parquet
data/cn_daily_alpha_all.parquet.factor_manifest.json
```

然后正常回测：

```bash
uv run moneytree \
  --config configs/market/cn.yaml \
  --config configs/model/xgb_regressor.yaml \
  --config configs/backtest/default.yaml \
  --data data/cn_daily_alpha_all.parquet \
  --output-dir artifacts/xgb-alpha-all
```

## Manifest

每次成功生成都会写 manifest，记录：

- 因子来源和家族。
- 输入/输出文件 hash。
- 输入/输出 schema 摘要。
- DolphinDB host、port、user、server version 和 Python client version。
- WQ101、GTJA191、`moneytreeAlpha` 模块版本标签。
- 价格、成交量、市值、行业和基准字段选择。
- fallback 字段和缺失可选字段。
- 列完整性和键匹配校验结果。

manifest 不记录密码、token、`.env` 内容或 TuShare token。

## 校验规则

生成脚本会拒绝以下情况：

- 输入面板存在重复 `date, ticker`。
- 请求 Alpha101 但输出缺少 `alpha101_001...alpha101_101` 中任意列。
- 请求 Alpha191 但输出缺少 `alpha191_001...alpha191_191` 中任意列。
- 输出包含请求范围外的 `alpha101_` 或 `alpha191_` 列。
- DolphinDB 返回了不在输入面板内的 `date, ticker`。
- 输出与输入没有任何匹配键，或匹配键上所有请求因子值都是空。

这些校验的目标是让外部因子生产保持为正式数据契约，而不是临时拼接。

## 研究风险

- `rank`、`ts_rank`、`decay_linear`、`SMA` 等算子在不同实现中可能有口径差异。
- `vwap`、复权价格、市值和行业分类会显著影响因子值。
- Alpha101 行业相关因子需要 point-in-time 行业分类。
- Alpha191 依赖的基准开收盘字段需要与回测基准一致。
- 不建议混用多个 Alpha101/191 实现来源后直接比较结果；应先固定 DolphinDB 和模块版本。
