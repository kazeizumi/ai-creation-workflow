# AI Creation Workflow

This repository contains the first combined release from September 2026. It bundled project orchestration, skill governance, and H3 runtime adapters in one package. The two core responsibilities now live in separate repositories:

- [`skill-router`](https://github.com/kazeizumi/skill-router) reviews, merges, updates, and retires Agent Skills.
- [`workflow-orchestrator`](https://github.com/kazeizumi/workflow-orchestrator) manages dependencies, versions, resumable work, and delivery across multi-stage projects.

The split removes an unnecessary routing step from ordinary tasks and keeps video runtime adapters out of the general workflow controller. Each Skill can now be installed and updated on its own.

Use `skill-router` when maintaining a skill library: overlapping triggers, upstream updates that conflict with local changes, or retirement of an old entry. Use `workflow-orchestrator` when one project stage affects another or work needs to resume across sessions. For a single self-contained task, use the relevant specialist Skill directly.

This repository remains available for its original combined package, H3 local/cloud adapters, and commit history. It is no longer the current release. New work belongs in the two repositories above.

If you installed `ai-creation-workflow` or `skill-governor` from this repository, remove the old entry before installing its replacement so both versions do not respond to the same request.

MIT License
