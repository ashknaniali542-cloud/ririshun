# 可验证经验契约

经验是独立 JSON 条目，按 `id/version.json` 或扁平文件存储均可。条目本身不成为全局系统指令；只有匹配当前任务时才供代理参考。示例模板在 `assets/experience-template.json`。

## 必填字段

- `schema_version=1`，`id` 小写字母数字连字符，`version` 为 x.y.z，`title`。
- `module`：routine/forecast/emergency/packing。
- `kind`：procedure 或 policy_hypothesis；`status`：draft/validated/rejected/deprecated。
- `source_scope` 与 `target_scopes`：来源及允许使用范围，使用 domain-rules 定义的枚举。
- `available_at`：带时区 ISO 时间。经验从这个时刻才可用于后续决策。validated 条目不得早于验证报告时间。
- `applicability`：适用上下文字段及精确值，例如 `inventory_rule=E_N_v1`、`forecast_model=shared730`、`controller=B`。检索上下文缺字段视作不匹配。
- `triggers`：字段、比较符 `eq/gt/gte/lt/lte/in`、值；全部成立才命中。关键词只排序，不能绕过触发条件。
- `evidence`：非空数组，每项有相对路径或绝对路径、SHA-256、依据说明。相对路径基于 `--base`（检索时为经验库目录）。不执行这些文件。
- `steps`：非空步骤数组；`constraints`：非空边界数组；`not_applicable`：不适用情况数组。
- `validation`：draft 可为 null；validated 必须指向哈希匹配的验证 JSON。

## 验证报告

`schema_version=1`、`entry_id`、`kind`、`result=pass`、`reviewer`、`validated_at`、`source_scope`、`target_scopes`、`applicability`、非空 `checks`。每项 check 包含 `name`、布尔 `passed` 与证据说明 `detail`。报告保留 `entry_content_sha256`，绑定经验内容而非仅绑定 id。

`procedure` 需要 `method=source_and_test` 或 `deterministic_audit`。它验证处置/检查方法，不证明经济收益。

`policy_hypothesis` 还需要 `method=heldout_replay`、`split=heldout/future_window`、`causal_cutoff_passed=true`、`constraint_checks_passed=true`、`baseline_run_id`、`candidate_run_id`、`comparison_scope`，并有 `metric.name/unit/baseline/candidate/direction`、`acceptance_passed=true`。数值须有限，且符合指标改善方向。应另附原始重放证据；脚本验证文件结构与一致性，不替代人工判断外部报告真实性。

`promote` 不自动编造报告，不覆盖旧条目。只有验证报告和所有证据存在、内容哈希匹配，才能输出 validated 版本。变更经验步骤后必须重做验证。

## 检索上下文

包含 `module`、`source_scope`、带时区 `knowledge_cutoff`、`query`，以及经验 applicability/triggers 要用到的业务字段。仅返回通过校验的 validated 条目；其他条目逐项列出排除理由。新旧版本都匹配时只选最高版本。

这是一套显式条件匹配检索，不是已经训练好的推荐模型，也不是向量检索服务。运行结果的 `executable=false` 表示检索不会自动执行调拨。
