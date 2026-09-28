# 公开发布审计

公开快照在进入 `quant-factor-observatory` 或 GitHub Pages 前必须满足以下条件：

1. `kind` 为 `moneytree_factor_evidence_snapshot`，`schema_version` 为受支持版本。
2. 所有数值都能以标准 JSON 编码；非有限值必须为 `null`。
3. 不存在 ticker、持仓、权重、原始路径或凭证字段。
4. 快照带有数据版本、样本区间、代码修订号（不可用时可以为 `null`）和计算配置。
5. 输入面板、原始缓存、因子仓库和回测产物不进入公开仓库。

推荐流程：

```text
硬盘盒/私有研究环境
        ↓
因子生成与证据计算
        ↓
公开字段审计
        ↓
静态 JSON 快照
        ↓
quant-factor-observatory / GitHub Pages
```

GitHub-hosted Actions 只负责构建已审核的文档和静态前端，不访问本地硬盘盒，也不运行需要真实数据或凭证的研究计算。
