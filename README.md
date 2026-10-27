# RRS Operations Learning

面向多仓运营的离线结果复核与经验管理方法工具。

当前发布版本：`vO.1.0`。详见 [发布说明](RELEASE_NOTES.md)。

本项目提供可运行的审查、经验校验、验证后晋级和条件检索程序，并附应用接入接口草案。**不包含企业数据、企业实验结果、私有模型或调拨求解器。** 演示数据由代码在运行时独立生成，未从业务记录抽取、扰动或截断。

## 1. 解决什么问题

预测、调拨和装载系统会产生大量结果，但结果口径、适用条件和经验有效性容易混淆。本项目帮助回答：账务与数量是否一致、证据是否变化、经验是否经过验证、能否在当前配置和决策时点使用。

运行逻辑为：已有结果 → 确定性复核 → 条件检索 → 可选的证据解释 → 经验草稿 → 独立验证 → 后续复用。实际预测、优化、物理装载和业务执行由外部系统承担。

## 2. 主要功能

| 功能 | 已实现内容 | 边界 |
|---|---|---|
| 日报复核 | 需求/销量/缺货、净贡献、连续日库存总量递推 | 不证明全部仓库/SKU 约束 |
| 车次复核 | 数量向量、路线、到货日、重量和体积 | 不等于三维装载认证 |
| 预测复核 | MAE、RMSE、WAPE、偏差和区间覆盖 | 当前单位为完成业务记录数，不训练预测模型 |
| 应急复核 | 目标分项、服务比例及上游有效标记 | 不重新执行物理检查 |
| 配对复核 | 重复配对、金额换算和差额汇总 | 不自动做显著性检验 |
| 经验校验/晋级 | 字段、证据 SHA-256、验证报告与经验内容绑定 | 不替代对外部报告真实性的审核 |
| 经验检索 | 状态、来源、时间、配置、触发条件过滤与关键词排序 | 无向量数据库，不自动执行经验步骤 |
| 方法演示 | 运行时生成小型人工表和经验，验证完整工具链 | 不代表实际经营效果 |
| Node 调用参考 | 超时/输出限制与 Python 子进程调用 | 无 HTTP 服务或任务队列 |

**尚未实现：** Web 页面、HTTP 路由部署、在线大模型连接、业务日志回传、自动训练、PPO 在线更新与自动发运。OpenAPI 和提示词文件是接入设计。

## 3. 安装

安装 Python **3.10 或以上**，解压本项目，保留目录结构，在根目录打开终端：

```sh
python --version
python -B "05_原始Skill/rrs-operations-learning/scripts/rrs_audit.py" --help
python -B "05_原始Skill/rrs-operations-learning/scripts/experience_store.py" --help
```

若系统命令是 `python3`，替换上述 `python`。核心工具和测试只使用标准库，无需 pip 依赖、API Key 或数据库。`-B` 用于避免字节码缓存。本项目不是 pip 包，也不包含完整 Web 应用。

Node 调用参考需要 Node.js 24 或以上，使用内置模块，无需 npm 安装。`RRS_PYTHON` 环境变量可指定解释器，默认调用 `python`。

若作为 Skill 使用，将 `05_原始Skill/rrs-operations-learning/` 整个目录放入代理工具支持的 Skill 目录。命令行运行无需先安装 Skill，安装 Skill 也不代表已经完成系统接入。

## 4. 快速使用

### 无需输入数据的演示

```sh
python -B "04_离线演示/run_demo.py"
```

程序生成五类微型人工表、三条经过演示检查的经验和一条未验证草稿，运行审查、晋级与检索，并验证跨来源和历史时间隔离。默认将临时文件写入系统临时目录，结束后自动清理。

如需保留**人工**结果，显式指定一个不存在的目录：

```sh
python -B "04_离线演示/run_demo.py" --out demo-output
```

保留的文件包括人工 CSV、绑定 JSON、audit.json、演示经验、检索结果和 summary.json。`demo-output/` 已列入忽略规则，不应作为业务证据公开。目录已存在时程序拒绝覆盖。

可选的 Node 调用演示：

```sh
node "03_接入参考/python-worker.mjs" --demo
```

此命令运行同一个人工演示，不启动服务器。

### 接入自己的数据

把授权数据放在本项目之外，准备本次绑定 JSON，再调用：

```sh
python -B "05_原始Skill/rrs-operations-learning/scripts/rrs_audit.py" --project-root demo-output --bindings demo-output/bindings.json --out reports/audit-001
```

上面命令复核前一步保留的人工结果；真实业务接入时替换输入目录和绑定文件。`--bindings` 必填，已移除私有默认绑定。

- 支持的数据键：`daily`、`trips`、`forecast`、`emergency`、`paired`。
- 每项包含相对 `path`、文件 `sha256` 和来源声明 `scope`。
- 注册 `trips` 时还需 `vehicle.kg`、`vehicle.m3`；上限由当前业务配置确定。
- 字段见 [dataset-fields.json](02_接口与数据/dataset-fields.json)。来源标签由接入方验证，脚本不会自动认证数据真实性。

输出 `audit.json` 和 `audit.md`；输出目录必须不存在。脚本不修改输入。

## 5. 输入与输出示例

### 预测复核

演示程序生成的人工预测输入：

```csv
node,date,actual,selected,lower,upper
demo-node,2020-01-01,10,12,8,16
demo-node,2020-01-02,20,18,15,24
```

`actual` 是人工构造的记录数，`selected` 是待评估预测，`lower/upper` 为区间。输出节选：

```json
{
  "dataset": "forecast",
  "declared_scope": "synthetic_development",
  "status": "PASS",
  "rows": 2,
  "binding_hash_matches": true,
  "metrics": {
    "MAE": 2.0,
    "RMSE": 2.0,
    "bias": 0.0,
    "interval_coverage": 1,
    "mean_interval_width": 8.5
  }
}
```

### 经验检索

保留演示后，输入 `demo-output/knowledge_base/contexts/forecast.json`：

```json
{
  "module": "forecast",
  "source_scope": "synthetic_development",
  "profile": "toy-v1",
  "knowledge_cutoff": "2020-01-04T00:00:00+00:00",
  "task": "result_review",
  "query": "review"
}
```

```sh
python -B "05_原始Skill/rrs-operations-learning/scripts/experience_store.py" retrieve --store demo-output/knowledge_base --context demo-output/knowledge_base/contexts/forecast.json --out reports/retrieval.json
```

命中条目的关键字段如下；完整输出还包含步骤、边界、证据和排除原因：

```json
{
  "executable": false,
  "matches": [
    {
      "id": "demo-forecast-review",
      "version": "1.0.0",
      "path": "entries/demo-forecast-review.json"
    }
  ]
}
```

演示条目的“validated”仅说明演示检查流程通过，不是企业现场验证。草稿或来源、配置、时间不符的条目不会命中。检索不执行经验步骤。

### 经验校验与晋级

模板在 [experience-template.json](05_原始Skill/rrs-operations-learning/assets/experience-template.json)。模板故意不带证据，直接校验应失败。自行准备草稿和验证报告后调用，下面路径仅为填写示例：

```sh
python -B "05_原始Skill/rrs-operations-learning/scripts/experience_store.py" check --entry experience-store/entries/draft.json --base experience-store
python -B "05_原始Skill/rrs-operations-learning/scripts/experience_store.py" digest --entry experience-store/entries/draft.json
python -B "05_原始Skill/rrs-operations-learning/scripts/experience_store.py" promote --entry experience-store/entries/draft.json --validation experience-store/validation/report.json --base experience-store --out experience-store/entries/validated.json
```

`procedure` 是检查流程；`policy_hypothesis` 是改变策略的假设，需独立重放、基线对照和约束检查。`promote` 只校验所提供的材料，不会运行策略实验或编造报告。详见 [经验契约](05_原始Skill/rrs-operations-learning/references/experience-contract.md)。

## 6. 测试和状态解释

```sh
python -B "05_原始Skill/rrs-operations-learning/scripts/test_skill_tools.py"
```

24 项行为测试覆盖数值一致性、证据篡改、来源/配置/时间隔离、草稿排除、相对路径与禁止覆盖。测试样例使用人工数据，在临时目录生成并逐项清理。`RRS_TEST_DIR` 可指定测试父目录，`RRS_DEMO_TMP_DIR` 可指定演示临时父目录；不要指向业务数据目录。

`PASS` 仅表示当前已实现检查没有报告异常；`FAIL` 表示异常；`NOT_CHECKED` 不能当通过。`binding_hash_matches=false` 需要重新核对证据。审查进程退出 0 不保证所有数据存在或所有哈希一致，接入方应读取报告。

证据哈希证明内容一致，不证明数据真实。重量/体积合格不等于几何可装，汇总守恒不等于全部 SKU 可执行。大模型、数据库、优化求解和实际执行认证均不属于当前工具的验证结果。

## 7. 接入与目录

- [系统接入说明](01_系统接入说明.md)：输入版本绑定、前后端职责与验收。
- [OpenAPI 草案](02_接口与数据/ai-review.openapi.json)：尚未部署的应用接口。
- [ReviewPort.ts](03_接入参考/ReviewPort.ts)：应用类型参考。
- [大模型提示词](03_接入参考/LLM_SYSTEM_PROMPT.md)：需要接入方实现供应商调用、结构检查和证据验证。
- `04_离线演示/`：演示入口；没有预置业务数据文件。
- `05_原始Skill/rrs-operations-learning/`：Skill、工具、模板与测试。
- `06_验证记录/`：本方法版的验证摘要。
- [来源说明](07_来源/来源与许可.md)：来源与分发边界。

`.gitignore` 排除了数据、运行报告、数据库、缓存和压缩包。输入真实数据时仍应将其放在公开目录之外；忽略规则不能替代公开前检查。旧版内部压缩包不属于本版本。

## 8. 许可证

项目的软件及相关文档采用 [MIT License](LICENSE)，版权署名为 `2026 RRS Operations Learning contributors`。

工作流参考 [Claudeception](https://github.com/blader/Claudeception)，保留 [上游 MIT 许可证](05_原始Skill/rrs-operations-learning/LICENSE) 与来源说明。企业业务数据不在本项目软件授权范围内；第三方内容保留其原有版权与许可。
