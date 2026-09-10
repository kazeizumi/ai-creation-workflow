# Skill 学习、评分与淘汰

技能管家要回答的不只是“这个 Skill 能不能用”，还要回答“它在真实任务里是否值得继续保留”。因此把生命周期拆成三类证据，不能用一个模糊总分代替：

1. **静态治理就绪度**：入口结构、触发条件、边界、引用、来源、许可证、脚本风险和版本映射是否完整。
2. **真实质量证据**：任务适配、产物质量、稳定性、效率、维护性、独特性和安全性。
3. **使用证据**：被选用、完成、部分完成、失败或被替代的任务记录。使用次数只能说明常用程度，不能直接说明质量。

## 生命周期

新 Skill 默认进入 `probation`，只能在限定场景中试用。它应当用同一个真实请求与当前主 Skill 做 A/B，对照输入、输出、稳定性和成本；不能只看候选 Skill 自带的示例或宣传描述。

每个工作阶段只分配一个主 Skill。只有主 Skill 存在明确缺口时，才增加专项或互补 Skill；`alternate` 默认不与 `primary` 同时运行。路由顺序是：

```text
交付物与输入适配
→ 平台、工具和授权
→ mapping=current
→ 当前阶段的唯一职责
→ 真实质量证据
→ 独特增益
→ token、时间和维护成本
```

建议状态及处理方式：

| 审计动作 | 含义 | 管家处理 |
|---|---|---|
| `keep-core` | 主流程、高适配、证据可靠 | 保持自动发现 |
| `keep-core-probation` | 主流程但当前版本证据不足 | 保留核心位并补足实测证据 |
| `keep-specialist` | 独特的窄领域能力 | 保留，收窄触发范围 |
| `trial-review` | 新装或证据不足 | 限定任务试用，积累证据 |
| `observe` | 有使用但表现不稳定 | 做定向回归 |
| `compare` | 与现有能力重复 | 用同题 A/B 决定主次 |
| `repair` | 映射、结构、断链或来源有问题 | 修复前不参与隐式路由 |
| `compatibility-review` | 当前环境或版本兼容性存疑 | 核对依赖与接口后再恢复自动选择 |
| `quarantine-review` | 多次低质或有安全缺陷 | 停止自动选择，等待处理 |
| `protected` | 系统或插件管理 | 只能查看，不能本地改写 |

## 什么时候记录学习结果

`record-use` 只记录一次真实任务中的归因使用结果；`record-outcome` 才记录质量评分。普通 direct/light 任务不必为了记账增加额外步骤，full 工作流复用已有节点信息即可。只有用户明确表扬、纠正、拒绝，独立回归，或出现可测量的质量/效率变化时，才写质量证据。

评分必须绑定当前 Skill 的行为指纹和稳定任务 ID。七个维度各用 1–5 分：`fit`（适配）、`output`（产物）、`reliability`（稳定）、`efficiency`（效率）、`maintainability`（维护）、`uniqueness`（独特性）、`safety`（安全），并注明 `pass`、`partial` 或 `fail` 以及证据来源。项目总评价不能复制给所有参与 Skill；原因不明时先定位是需求、选型、交接、专业方法还是工具执行问题。

示例：

```powershell
python skills/skill-governor/scripts/skill_registry.py record-outcome `
  --skill h3-runtime-router `
  --task-id project-001-G01 `
  --fit 5 --output 5 --reliability 4 --efficiency 4 `
  --maintainability 5 --uniqueness 4 --safety 5 `
  --verdict pass `
  --source user `
  --evidence "按要求完成云端/本地决策，生成契约可直接交给执行器" `
  --artifact artifacts/project-001/runtime-contract.md
```

更新 Skill 后，旧证据保留为历史，新版本重新进入 `probation`。这样可以区分“这个版本表现好”和“这个名字过去表现好”。

## 评分和审计

```powershell
python skills/skill-governor/scripts/skill_audit.py record-use `
  --skill h3-runtime-router `
  --task-id project-001-G01 `
  --result completed `
  --reason "输出运行时选择和生成契约"

python skills/skill-governor/scripts/skill_audit.py audit `
  --output-json skill-audit.json `
  --output-md skill-audit.md
```

审计会合并静态就绪度、当前版本质量任务、近期使用和重叠组，输出保留、试用、观察、对比、修复、隔离审查或受保护建议。静态审计只是初筛；`trial-review` 表示证据不足，不等于低质量。

## 淘汰门禁

只有同时满足以下条件，管家才会把 Skill 列入“建议退役”：

1. 已有通过测试的替代者；
2. 独特能力已经迁移，或已确认没有保留价值；
3. 同题 A/B 中替代者不劣于原 Skill；
4. 近期使用、用户依赖和历史项目引用已经核对；
5. 许可证允许必要的整合；
6. 已建立日期化、可恢复的备份。

管家只生成候选清单和影响说明。移动、停用、合并或删除仍需用户明确批准；实际淘汰优先移入日期化归档，不永久删除，并写入 `registry/skill-retirements.json`，让后续审计知道它是“主动可恢复退役”而不是从未安装。

执行 `prepare-retire` 前复制并完整填写
`assets/templates/retirement-evidence.json`。任一替代测试、独特能力处置、
同题 A/B、近期使用、项目依赖或许可证字段缺失，计划都不能进入
`ready`；准备后证据文件或 Skill 行为指纹发生变化，也必须重新准备。

建议在新装或更新后做结构、来源、重叠和前向测试；真实任务后按需记录归因证据；技能库明显变大或用户要求时做全库审计；淘汰前做深度审阅、A/B、依赖检查和用户闸门。不自动创建定时任务。
