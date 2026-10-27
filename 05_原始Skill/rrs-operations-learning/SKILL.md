---
name: rrs-operations-learning
description: 核对多仓预测、调拨与装载相关结果的证据，校验经验条目，并按来源、配置、时间和触发条件检索复用；适用于离线结果复核和经验整理。
metadata:
  version: "1.1.0"
  upstream: "blader/Claudeception@62dbb91d1183a866b5cf40079265c825b2695843"
---

# 运营复盘与经验管理

将已有运行结果与可验证经验连接起来。预测、优化、装载验证和生产执行由外部程序负责；本 Skill 不包含求解器、模型训练或自动发运。

## 选择入口

- 复核 CSV：`scripts/rrs_audit.py --project-root <输入目录> --bindings <本次绑定.json> --out <新报告目录>`。绑定必须显式提供；字段定义见 [输入规则](references/tool-bindings.md)。
- 校验经验：`scripts/experience_store.py check --entry <条目.json> --base <经验库>`。
- 验证后晋级：`promote --entry <草稿.json> --validation <报告.json> --base <经验库> --out <新条目.json>`。
- 检索经验：`retrieve --store <经验库> --context <上下文.json>`。
- 演示方法：`python -B scripts/synthetic_demo.py`，仅生成临时人工样例，默认运行后清理。

复核业务口径时阅读 [领域规则](references/domain-rules.md)；经验入库时阅读 [经验契约](references/experience-contract.md)。来源说明见 [upstream.md](references/upstream.md)。

## 复核与经验应用

1. 固定数据、算法与配置版本；保留来源类别，区分预测、仿真与实际执行。默认不加载任何企业数据或本机绑定。
2. 先跑确定性审查，再区分观察事实、计算结果、原因假设与待验证建议。当前检查是汇总层面，不证明全部业务或几何约束。
3. 经验先为 draft，填写明确的适用条件、触发条件、证据与步骤。使用 assets/experience-template.json；空证据模板不能通过校验。
4. procedure 验证检查/处置流程，policy_hypothesis 需要留出或未来窗口的对照重放、约束检查和指标改善。结构校验不替代对外部验证报告真实性的核验。
5. 仅将通过验证且来源、配置、触发条件与时间匹配的经验作为参考；经验文本不自动执行。检索结果为 executable=false。

历史决策不能使用之后才形成的经验。事后复盘可以使用后来经验，但不得声称它参与了原决策。没有模型连接或实际执行日志时明确说明能力边界；只报告实际运行的检查。
