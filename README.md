# AI Creation Workflow

这个仓库是 2026 年 9 月发布的第一版组合包，当时把项目总控、技能治理和 H3 执行器放在了一起。实际使用后，两个核心职责已经拆开：

- [`skill-router`](https://github.com/kazeizumi/skill-router)：管理 Skill 的比较、融合、更新和退役；
- [`workflow-orchestrator`](https://github.com/kazeizumi/workflow-orchestrator)：管理多阶段任务的依赖、版本、续作和交付。

新版本不再让每个普通任务先经过技能管家，也不再把 AI 视频执行器绑在通用总控里。两个 Skill 可以分别安装，职责和更新节奏都更清楚。

## 该用哪个

如果你在整理技能库，例如两个 Skill 重复、上游更新和本地改动冲突，或准备删除旧入口，请使用 `skill-router`。

如果你在做一个有前后依赖的项目，例如剧本确认后进入导演、资产和生成，或任务需要跨会话恢复，请使用 `workflow-orchestrator`。

单项任务直接使用对应的专业 Skill，不需要额外安装这两个入口。

## 这个仓库怎么处理

仓库保留原组合包、H3 本地/云端执行器和提交历史，方便旧链接继续打开，也方便需要执行器代码的人查阅。它不再作为当前版本维护；后续更新分别进入上面的两个仓库。

如果你已经从这里安装了 `ai-creation-workflow` 或 `skill-governor`，请先移除旧入口，再安装对应的新仓库，避免自动触发时出现重复职责。

MIT License
