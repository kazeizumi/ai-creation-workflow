# Two top-level roles

The package has one outward-facing project workflow and two cooperating roles.

| Role | Owns | Does not own |
|---|---|---|
| Skill governor | Skill discovery, install, route, allocation, source, quality evidence, overlap, update, backup and rollback | Project schedule, creative deliverables, stage completion or user progress |
| Workflow controller | Goal, requirements, execution plan, detailed steps, dependencies, handoffs, gates, progress, validation and delivery | Skill portfolio mutation or inventing a specialist's craft method |

The workflow controller asks the governor for an assignment when it creates or
revises a stage. The governor returns a small routing decision, not a second
project plan. The workflow controller then reads the selected skill, runs the
step, checks the output and updates project state.

AI video is one domain under the workflow controller. Its script, shot, prompt,
reference, H3 and media-QA steps are examples of stages. The H3 router, local
runner, cloud runner and AutoDL adapter are execution support for those stages.
