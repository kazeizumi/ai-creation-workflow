# Token and delegation policy

The default policy is `on`: reduce repeated context, tool work and status text
while preserving the requested result, the complete instructions of the active
specialist skill, required authorization and artifact validation. Do not use an
ultra-short mode for production instructions, executable manifests or handoffs.

## Context tiers

| Tier | Use | Context behavior |
|---|---|---|
| `compact` | Direct and small light tasks | Current request, authoritative inputs, one active skill and its required references |
| `standard` | Full workflows and normal production | Project contract, decision index, current stage packet and direct dependencies |
| `expanded` | A real ambiguity, failure investigation or cross-stage validation | Add only the affected upstream evidence and competing methods |

Start at the smallest tier that can satisfy the output. Expand when a concrete
dependency or failed check requires it; never reduce context by dropping a fact
that controls identity, continuity, cost, authorization or acceptance.

## Canonical context

Store stable facts once in the project contract or decision index. Downstream
steps reference the artifact path, version or decision ID instead of copying its
body. A current-stage packet contains only:

```text
current deliverable and stop point
authoritative input references and versions
confirmed decisions and constraints
missing information that blocks this stage
target tool and current authorization
acceptance evidence and failure rule
```

Completed stages keep their output path, version and short result. Reopen their
full contents only when the current stage consumes them or a fingerprint has
changed.

## Skill and tool loading

1. Load the complete `SKILL.md` only for the skill being executed now.
2. Load only the references selected by that skill for the current branch.
3. List future specialists and duties in the plan without loading them early.
4. Skill allocation remains owned by `skill-governor`, but reuse an accepted
   allocation when lane, input type, tool, constraints and mapping fingerprint
   are unchanged.
5. Query or rescan the governor when a new capability is needed, candidates
   compete, a mapping is stale, the tool changes, or the selected skill fails.
6. Batch independent searches and reads. Do not repeat a broad read when a
   targeted range answers the new question.
7. Record evidence only for a material, attributable result; do not create a
   second daily ledger for direct or light tasks.

## Subagent decision

Evaluate delegation when a full workflow has at least two `ready` nodes. Create
a subagent only when every condition below is true:

- the node can finish without an unresolved user decision or another running
  node's output;
- it has a precise input packet, output contract and observable acceptance;
- its write targets and external resources do not overlap another writer;
- independent work is large enough that parallel execution or specialist focus
  is expected to save more time or total context than coordination consumes;
- the current runtime rules authorize subagents.

Keep work in the root agent when stages are sequential, several steps edit the
same artifact, the task is small, the goal is still ambiguous, one shared
runtime must be controlled serially, or the root must immediately integrate
every intermediate decision.

The number of skills is not a reason to create the same number of agents. A
subagent owns one bounded deliverable, not an entire duplicate project.

## Minimal subagent packet

Send only:

```yaml
node_id: stable-stage-id
deliverable: exact artifact or finding
stop_point: what must not be changed
inputs:
  - path_or_id: authoritative reference
    version: current version
decisions: [relevant-decision-ids]
constraints: [only constraints affecting this node]
skills: [selected skill and unique duty]
write_scope: [non-overlapping targets]
acceptance: [observable checks]
failure_return: evidence required when blocked
```

The root agent remains the only user-facing coordinator. It receives the
artifact and evidence, validates the contract, integrates the result and updates
project state. Do not pass the full conversation when this packet is sufficient.

## Quality guard

Token reduction must not skip:

- requirement clarification that prevents direction-wide rework;
- complete reading of an actively selected skill;
- exact generation workflow, inputs, cost, output and recovery authorization;
- tests or media inspection required by the acceptance contract;
- state recovery before retrying an external job;
- user judgment for creative approval or irreversible changes.

If the compact route fails an acceptance check, expand only the affected stage,
repair it, and preserve independent completed work.
