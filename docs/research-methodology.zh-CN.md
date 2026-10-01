# 研究方法与证据边界

[English page](research-methodology.md)

Money Trees 负责因子计算和聚合证据生产；正式组合、执行模拟与风险归因由
`quant-platform` 和 `quant-backtest-runtime` 负责。研究结果必须绑定一个明确的
information set，不能把未来可见的数据用于特征、标签或决策。

## 最低研究契约

每次研究运行应记录：

- 数据版本、源元数据清单的 SHA-256 和代码 revision；
- feature cutoff、publication cutoff、decision time 和 execution time；
- 训练区间、标签区间、预测 horizon、purge window 和 embargo；
- 因子候选数量、调参次数、留出验证是否被查看，以及停止原因。

## 时间序列验证

有重叠标签时，普通随机交叉验证会把测试标签的信息泄漏到训练区间。正式验证
应使用按时间排序的 walk-forward folds，并从训练集剔除与测试标签重叠的事件，
再应用 embargo。Money Trees 可以生成候选因子证据，但 purge/embargo 的共享
实现和验证 receipt 属于 `quant-platform`。

## 不确定性与尾部风险

平均 IC 或累计收益不是充分证据。正式报告应尽可能包括 block bootstrap 或其
他依赖感知的不确定性、有效样本数、最大回撤、VaR/CVaR 和成本敏感性。没有
这些诊断时，`factor_evidence.v1` 会将对应 section 标记为 `not_provided`，
不会把缺失诊断解释成通过。

前瞻收益持有期明确时，公开 Alpha 证据生成器会用 Newey–West HAC 估算每日 RankIC 均值的不确定性，
滞后阶数为持有期减一个交易日，缺失日期保留原序列位置，区间采用双侧标准正态参考分布。完整声明
因子族的多重检验以 Benjamini–Yekutieli 作为主要校正；不可计算的检验仍计入分母，但不分配 q 值。
这些检验只涉及预测性 RankIC，不能替代组合层面的风险、成本和执行分析。

## 残差与公开发布

因子在控制规模、波动、流动性或行业暴露后仍需检查 residual predictability。
公开站点只接收聚合结果，不接收逐股票信号、组合权重、原始路径或供应商字段。
`factor_evidence.v1` 是研究层到 Observatory 的统一聚合契约。
