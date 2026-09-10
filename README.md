# AI Creation Workflow

[English](README.en.md)

这个仓库管两件容易失控的事：长流程 AI 项目，以及越装越多的 Skill。

`ai-creation-workflow` 负责项目怎么往下走，`skill-governor` 负责每一步该用哪个 Skill、现有能力够不够。它们可以单独安装，也可以一起用。

仓库还带了一套 H3 视频执行工具，支持本机 ComfyUI 和 AutoDL 云端实例。这里提供的是流程、状态管理和执行适配器，不包含模型权重、第三方工作流或商业素材。

## 先看这里

- 想直接安装：看[安装](#安装)。
- 想做一个多阶段项目：看[项目总控](#项目总控)。
- 想整理、补强 Skill：看[技能管家](#技能管家)。
- 已经备好 H3 提示词和参考图：看[运行-h3](#运行-h3)。
- 想知道它和其他方案有什么不同：看[同类产品对比](docs/competitive-analysis.md)。

## 里面有什么

| Skill | 用途 |
|---|---|
| `ai-creation-workflow` | 拆阶段、管依赖、保存状态、恢复任务、验收交付 |
| `skill-governor` | 选择 Skill、判断能力缺口、查重、试用、更新和退役 |
| `h3-runtime-router` | 决定 H3 走本地还是云端，并整理生成前契约 |
| `comfyui-local-runner` | 按 JSON 清单调用本机 ComfyUI API |
| `minimax-h3-cloud` | 批量提交云端 H3 工作流、轮询并下载结果 |
| `autodl-app-instance` | 查询、启动和关闭 AutoDL 应用实例 |

两个核心 Skill 的分工：

```text
用户目标
  ↓
ai-creation-workflow 拆任务、排顺序
  ↓
skill-governor 为当前步骤找合适能力
  ↓
专业 Skill 或执行器完成工作
  ↓
总控验收结果并更新状态
```

![整体结构](docs/images/system-architecture.svg)

## 安装

需要 Python 3.11 或更高版本。

```powershell
git clone https://github.com/kazeizumi/ai-creation-workflow.git
cd ai-creation-workflow
python scripts/install.py --dry-run
python scripts/install.py --yes
```

`--dry-run` 只显示安装计划。正式安装默认写入 `~/.agents/skills`；已有同名 Skill 时，安装器会先备份到 `.ai-creation-workflow-backups`。

只装两个核心 Skill：

```powershell
python scripts/install.py `
  --skill ai-creation-workflow `
  --skill skill-governor `
  --yes
```

指定安装目录：

```powershell
python scripts/install.py --target "D:\MyAgent\skills" --yes
```

云端 H3 执行还需要 `httpx`：

```powershell
python -m pip install -r skills/minimax-h3-cloud/requirements.txt
```

安装后如果 Agent 没有立即显示新 Skill，刷新技能列表或重新开始一个会话。

## 项目总控

`ai-creation-workflow` 适合有前后依赖、可能中断恢复，或者涉及付费执行的任务。单个明确步骤不会强行建项目。

```text
使用 $ai-creation-workflow，把这份锁定剧本做成 16:9 AI 叙事短片。
需要镜头表、H3 中英文提示词、参考图上传顺序和最终视频。
```

它按任务规模选择三种模式：

| 模式 | 什么时候用 |
|---|---|
| Direct | 单个明确步骤，直接交给专业 Skill |
| Light | 少量有关联的步骤，在会话中保存简短检查点 |
| Full | 跨阶段、批量、付费或需要长期恢复的项目 |

Full 模式使用 Skill 内置的控制文件：

```text
skills/ai-creation-workflow/assets/templates/00-project-control.md
skills/ai-creation-workflow/assets/templates/workflow-state.json
```

上游材料变化时，总控只让真正依赖它的阶段失效，不会推倒整个项目。状态文件可以直接检查：

```powershell
python skills/ai-creation-workflow/scripts/workflow_state.py `
  validate workflow-state.json
```

细节在下面几份文档里：

- [需求和审批门](skills/ai-creation-workflow/references/intake-and-gates.md)
- [项目控制](skills/ai-creation-workflow/references/project-control.md)
- [Token 和子代理](skills/ai-creation-workflow/references/token-and-delegation.md)

### AI 视频流程

内置的 `ai-video` 领域包大致按下面的顺序工作：

```text
剧本 → 镜头 → 生成段 → 参考材料 → 提示词
     → 本地或云端渲染 → 媒体验收 → 剪辑与声音
```

单个镜头可以走快速路径，不必创建整套台账。批量里有高风险镜头时，先生成一条代表样片，再决定是否继续铺开。

查看领域包：

```powershell
python skills/ai-creation-workflow/scripts/domain_pack.py list
python skills/ai-creation-workflow/scripts/domain_pack.py show --pack ai-video
```

## 技能管家

`skill-governor` 解决的不是“再装一个 Skill”，而是先判断有没有必要装。

每次分配前，它把现有能力分成三种情况：

- `fit`：现有 Skill 能独立完成，直接使用。
- `partial`：能做一部分，继续找缺的那一块。
- `gap`：本地没有合适能力，再考虑网上的候选。

默认顺序是：复用已有结论，检查本地 Skill，确认缺口后才搜索 GitHub 仓库元数据。搜索最多保留 5 个候选，只深读最后 1–3 个；`resolve` 本身不会下载或安装任何内容。

如果用户直接给了 Skill 名称、路径、压缩包或网址，就跳过搜索，但查重、安全、许可证和兼容性检查仍然保留。

候选审查后会给出一种建议：

| 建议 | 条件 |
|---|---|
| `full_install` | 能力边界独立，确实增加了可测试的新功能 |
| `reference_strengthen` | 和现有 Skill 重叠较多，只吸收有用且许可允许的部分 |
| `reject` | 没有实际增益，或安全、许可证、依赖成本不合格 |

用户已经说明选择时，不会再问一遍。没有说明时，只问一次：“完整安装，还是参考后补强现有功能？”

能力判断和候选建议：

```powershell
python skills/skill-governor/scripts/capability_gap.py assess `
  --request capability-request.json `
  --output routing-decision.json

python skills/skill-governor/scripts/capability_gap.py resolve `
  --request capability-request.json `
  --decision routing-decision.json `
  --output gap-resolution.json

python skills/skill-governor/scripts/capability_gap.py adopt `
  --review candidate-review.json `
  --output candidate-adoption.json
```

已有决策和输入指纹没变时，结果会直接复用，避免重复搜索和重复审读。详细规则在 [capability-gap.md](skills/skill-governor/references/capability-gap.md)。

### 扫描现有 Skill

```powershell
python skills/skill-governor/scripts/skill_registry.py scan
python skills/skill-governor/scripts/skill_registry.py report --include-unready
python skills/skill-governor/scripts/skill_registry.py duplicates
python skills/skill-governor/scripts/skill_registry.py validate
```

默认读取共享 Skill、系统 Skill，以及当前启用插件暴露的 Skill。仓库自带的 roadmap 只登记本项目组件，不会替你补完整个技能库的路由表。

### 更新和退役

新 Skill 先进入 `probation`。它需要在真实任务中和现有方案做同题比较，有证据后才进入主路由。

退役也不会直接删除。替代方案通过测试、独特能力已经处理、项目依赖和许可证都核对过后，工具才能生成退役计划。真正移动文件仍需要明确批准，并保留恢复记录。

```powershell
python skills/skill-governor/scripts/skill_transaction.py prepare --help
python skills/skill-governor/scripts/skill_transaction.py backup --help
python skills/skill-governor/scripts/skill_transaction.py activate --help
python skills/skill-governor/scripts/skill_transaction.py rollback --help
python skills/skill-governor/scripts/skill_transaction.py prepare-retire --help
python skills/skill-governor/scripts/skill_transaction.py restore-retired --help
```

评分、来源和退役证据的完整说明见 [evolution.md](skills/skill-governor/references/evolution.md)。

![Skill 治理流程](docs/images/skill-governance-cycle.svg)

## 运行 H3

提示词和参考材料准备好后，先用 `h3-runtime-router` 确认走本地还是云端。用户已经指定时不会重复提问。

真正提交前，要明确工作流、输入、上传顺序、生成范围、输出位置和失败后的处理方式。云端任务还要确认实例、费用估算和关机策略。

### 本地 ComfyUI

本地执行器要求 ComfyUI 已经运行，并且工作流已经导出成 API Format JSON。最小清单见 [local-h3-job.json](examples/minimal-project/local-h3-job.json)。

先离线检查：

```powershell
python skills/comfyui-local-runner/scripts/run_local.py `
  examples/minimal-project/local-h3-job.json `
  --dry-run
```

确认后去掉 `--dry-run` 才会提交。运行状态写在 `run-state.json`；超时后应先按已有 `prompt_id` 查结果，不要直接重发。

### AutoDL 云端

Token 从当前进程的 `AUTODL_TOKEN` 读取，也可以放在本机的 `~/.config/autodl.env`。不要把它写进仓库、任务清单或命令参数。

常用实例命令：

```powershell
python skills/autodl-app-instance/scripts/autodl_instance.py list
python skills/autodl-app-instance/scripts/autodl_instance.py status --uuid pro-xxxxxxxxxxxx
python skills/autodl-app-instance/scripts/autodl_instance.py boot --uuid pro-xxxxxxxxxxxx
python skills/autodl-app-instance/scripts/autodl_instance.py off --uuid pro-xxxxxxxxxxxx --wait
```

实例启动后，先读取这次返回的面板地址，再检查实际存在的工作流。不要沿用上次开机的旧 URL 或节点映射。

```powershell
$env:SEETACLOUD_BASE_URL = "https://本次返回的面板地址"

python skills/minimax-h3-cloud/scripts/workflow_tool.py list `
  --base-url $env:SEETACLOUD_BASE_URL

python skills/minimax-h3-cloud/scripts/workflow_tool.py inspect `
  --base-url $env:SEETACLOUD_BASE_URL `
  --workflow-id "准确的工作流ID" `
  --out workflow-map.json
```

批量清单示例在 [cloud-h3-batch.json](examples/minimal-project/cloud-h3-batch.json)。同样先 dry-run：

```powershell
python skills/minimax-h3-cloud/scripts/run_batch.py `
  examples/minimal-project/cloud-h3-batch.json `
  --dry-run
```

正式运行会逐条保存 `prompt_id`，下载时先写 `.part` 文件，并按清单设置决定任务后是否关机。已有状态文件时默认拒绝重复提交；使用 `--resume` 只恢复已经记录的远端任务。

## 几个用法

完整项目：

```text
使用 $ai-creation-workflow 完成这个 AI 短片项目。
先复用现有剧本和角色资料。真正生成前让我选择云端或本地，
并说明预计费用、输出位置和失败回退。
```

只运行一段 H3：

```text
使用 $h3-runtime-router 执行这段 10 秒 H3 视频。
工作流、提示词和参考图在 project/G01，结果放到 project/results。
```

整理技能库：

```text
使用 $skill-governor 扫描我的共享 Skill，
列出未映射、已经变化和可能重复的能力。先给审计结果，不自动覆盖。
```

## 不会自动做的事

- 没有当前任务授权时，不提交 ComfyUI 或付费云端生成。
- 不因网络搜索结果看起来合适就自动安装。
- 不把“命令成功退出”当作视频验收完成。
- 不在超时后直接重发可能仍在运行的任务。
- 不永久删除 Skill，也不释放 AutoDL 实例。
- 不提交 Token、密码、签名 URL、客户素材或私有参考文件。

## 仓库结构

```text
skills/                     六个可安装 Skill
templates/                  核心模板的浏览副本
examples/minimal-project/   可离线检查的最小示例
scripts/install.py          带备份的安装器
scripts/verify_release.py   发布检查
docs/                       机制说明、对比和设计记录
.github/workflows/ci.yml    Windows / Linux 验证
```

## 开发和验证

```powershell
python scripts/verify_release.py
python skills/skill-governor/scripts/skill_registry.py package-check
python skills/skill-governor/scripts/test_skill_governor.py
python skills/skill-governor/scripts/test_skill_lifecycle.py
python skills/skill-governor/scripts/test_capability_gap.py
python skills/ai-creation-workflow/scripts/test_domain_pack.py
python skills/ai-creation-workflow/scripts/test_workflow_state.py
python scripts/test_installation.py
python scripts/test_runtime_guards.py
```

CI 在 Windows 和 Linux 上测试 Python 3.11、3.13。发布检查还会检查 JSON、Python 语法、内部链接、缓存文件、疑似凭据和私有绝对路径。

## 项目说明

- [同类产品对比与后续方向](docs/competitive-analysis.md)
- [改进计划和完成情况](docs/competitive-improvement-plan.md)
- [实现与验收记录](docs/pending-execution-plan.md)
- [第三方来源与改写说明](NOTICE.md)

许可证：MIT。
