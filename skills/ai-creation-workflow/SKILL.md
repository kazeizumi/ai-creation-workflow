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
  control file from `assets/templates/00-project-control.md` and a state file
  from `assets/templates/workflow-state.json`. These assets travel with an
  independently installed Skill; do not depend on repository-level templates.

## Run the project

1. Reuse current conversation, existing project files, and confirmed choices.
2. Define the outcome, deliverables, constraints, acceptance evidence and items
   explicitly outside scope. Resolve only missing facts that materially change
   goal, scope, cost, permission or an irreversible result.
3. Send each stage's required output, inputs, target tool, constraints,
   permissions and acceptance evidence to `skill-governor`. It returns the
   primary Skill, any necessary specialist, the boundary between them and
   missing inputs. If it returns `partial` or `gap`, let it finish the bounded
   local/online/create-or-improve loop before continuing this stage.
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

## Token and delegation

Use an adaptive context budget. Direct and light work starts compact; full work
loads the project contract, decision index, current stage and its direct
dependencies. Store stable facts once and pass references plus versions instead
of copying artifact bodies into every handoff.

Skill allocation remains owned by `skill-governor`. Reuse its accepted decision
while the lane, input type, tool, constraints and mapping fingerprint are
unchanged. Rescan or reroute only for a new capability, competing candidates,
mapping drift, a tool change or a failed assignment. Load the full instructions
only for the skill executing the current stage; do not preload future skills.

Evaluate subagents only when a full workflow has at least two independent ready
stages. Delegate a bounded artifact when inputs and acceptance are complete,
writes and external resources do not overlap, no unresolved decision blocks it,
parallel work is expected to reduce total cost, and current runtime rules allow
delegation. Keep sequential work, shared-artifact edits, ambiguous requirements
and small tasks in the root agent. The root owns user communication, integration
and final validation.

## Domain pack routing

Select a domain pack only after the project contract is clear. A pack contributes
stage templates, specialist lanes, domain gates and runtime adapters; it never
owns the overall project or replaces `skill-governor`. Validate installed packs
with `python scripts/domain_pack.py validate` and read
[references/domain-packs.md](references/domain-packs.md) before adding one.

Match the request to a pack's triggers, load only that pack and its linked guide,
and send each declared specialist lane or runtime capability to
`skill-governor`. The pack names required capabilities; the governor maps them
to current installed Skills.

## State rules

- A stage is `pending`, `ready`, `running`, `blocked`, `review`, `accepted`,
  `failed`, or `stale`; do not mark it accepted without its declared evidence.
- Store stable decisions once and reference them downstream. When a decision
  changes, mark only stages that consumed the changed input and their real
  dependants `stale` before rerunning them. Use
  `scripts/workflow_state.py invalidate` for a persisted state file.
- Retries preserve the original job identity and result directory. Never submit
  a second paid job merely because polling timed out; query by prompt or job ID.
- Keep secrets and private media outside project state. Store references to
  environment variable names and local files instead.

Read [references/task-contract.md](references/task-contract.md) when creating a
contract, [references/project-control.md](references/project-control.md) for a
resumable project, and [references/gates-and-evidence.md](references/gates-and-evidence.md)
before executing or closing a costly stage. Read
[references/intake-and-gates.md](references/intake-and-gates.md) when requirements
are incomplete or a gate may be needed. Read
[references/role-model.md](references/role-model.md) when allocating Skill
ownership or handing a stage to the governor. Read
[references/token-and-delegation.md](references/token-and-delegation.md) when
creating a full project, deciding whether to delegate, or reducing context use.
