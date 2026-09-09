---
name: ai-creation-workflow
description: Orchestrate an AI creative project from existing context and project setup through requirement completion, specialist-skill routing, stage dependencies, quality and execution gates, generation, validation, delivery, and reusable evidence. Use for end-to-end or cross-stage creative work rather than one isolated edit.
---

# AI creation workflow

Own the project plan and its execution. Ask `skill-governor` to allocate the
best installed skill for each stage, then sequence those assignments, preserve
their outputs, and keep one project state from planning through delivery.

## Choose the smallest control mode

- **Direct:** one clear reversible step; invoke the known specialist and return.
- **Light:** two to four dependent stages; keep a short in-chat contract and
  checkpoints.
- **Full:** cross-stage production, paid generation, multiple deliverables,
  repeated runs, handoffs, or work that may resume later. Create a project
  control file from `templates/00-project-control.md` and a state file from
  `templates/workflow-state.json`.

## Run the project

1. Reuse current conversation, existing project files, and confirmed choices.
2. Define the outcome, deliverables, constraints, acceptance evidence and items
   explicitly outside scope. Resolve only missing facts that materially change
   goal, scope, cost, permission or an irreversible result.
3. Send each stage's required output, inputs, constraints and acceptance evidence
   to `skill-governor`. It returns the primary Skill, any necessary specialist,
   the boundary between them and missing inputs.
4. Build a dependency graph and write those assignments into the plan. Each
   stage has one primary skill, optional complementary skills, inputs, output
   contract, validator and retry rule.
5. Execute the next ready stage. Save material outputs before moving downstream.
6. Apply gates at creative lock, paid generation, external publication and
   other irreversible actions. A gate names the exact decision and its impact.
7. Validate the artifact itself. A successful command is supporting evidence,
   not proof that a media result is correct.
8. Close out with final files, validation evidence, known limits and state.
   Record skill-use evidence only when it reflects an actual task result.

## AI video routing

Read [references/ai-video.md](references/ai-video.md) for the production graph.
When the execution model is MiniMax H3, delegate runtime selection and generation
authorization to `h3-runtime-router`. Prompt quality, references and storyboard
approval do not authorize a ComfyUI submission.

## State rules

- A stage is `pending`, `ready`, `running`, `blocked`, `review`, `accepted`, or
  `failed`; do not mark it accepted without its declared evidence.
- Store stable decisions once and reference them downstream. When a decision
  changes, mark every dependent stage stale before rerunning it.
- Retries preserve the original job identity and result directory. Never submit
  a second paid job merely because polling timed out; query by prompt or job ID.
- Keep secrets and private media outside project state. Store references to
  environment variable names and local files instead.

Read [references/task-contract.md](references/task-contract.md) when creating a
contract, [references/project-control.md](references/project-control.md) for a
resumable project, and [references/gates-and-evidence.md](references/gates-and-evidence.md)
before executing or closing a costly stage. Read
[references/role-model.md](references/role-model.md) when allocating Skill
ownership or handing a stage to the governor.
