# 数据与工具入口

所有命令仅依赖 Python 标准库。不分发企业数据、私有模型、算法源码绑定或默认真实输入。

## 审查绑定

`rrs_audit.py --project-root <输入目录> --bindings <配置.json> --out <新目录>`

绑定包含 datasets；每项必须有 path、sha256、scope。path 相对于 project-root。允许的数据键是 daily、trips、forecast、emergency、paired；注册 trips 时还需 vehicle.kg 和 vehicle.m3。详细必填列可直接查看 scripts/rrs_audit.py 的对应检查函数。

- daily：全网日报恒等式和连续日库存总量。
- trips：整数件数、数量向量、路线与到货日、重量和体积。
- forecast：actual、selected、lower、upper 数值及 node/date；单位约定为完成业务记录数。
- emergency：目标分项、缺口与满足量、服务比例、上游有效标记。
- paired：配对标识、金额换算及差额汇总。

输出 audit.json 与 audit.md。FAIL 表示当前检查发现问题；NOT_CHECKED 与哈希不一致也要单独处理，不能只看进程退出码。

## 外部算法

本包没有预测、调拨优化或几何装载求解实现。接入方提供对应服务并核验参数、单位与返回证据；没有接口时不得假装已计算。

## 自包含演示

`python -B scripts/synthetic_demo.py` 在临时目录生成五类微型人工表及演示经验，验证后清理；`--out <不存在的目录>` 可显式保留人工结果。这些参数不代表业务默认配置。
