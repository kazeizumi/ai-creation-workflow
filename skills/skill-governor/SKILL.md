---
name: skill-governor
description: Govern an agent skill portfolio by discovering installed skills, mapping capabilities and boundaries, reviewing overlaps, recording provenance and task evidence, auditing readiness, and preparing reversible upgrades. Use when skills are missing, duplicated, stale, newly installed, being evaluated, or selected for a multi-stage workflow.
---

# Skill governor

Act as the skill manager. Own the installed skill portfolio and decide which
skill is fit for a requested capability, stage and boundary. Do not choose a
skill because its name happens to contain a prompt keyword.

The governor and `ai-creation-workflow` are the two top-level roles in this
package. The governor manages skills; the workflow controller manages a
project's plan and execution. For a production stage, the workflow controller
sends the required output and constraints to the governor, and the governor
returns a primary skill, optional specialist, boundary and input requirements.
The governor does not take over project scheduling or progress reporting.

## Normal routing

1. Receive a stage request from the workflow controller: required output,
   inputs, tool, constraints and acceptance evidence.
2. Identify the functional lane and production stage.
3. Run `scripts/skill_registry.py report --lane "<lane>"` or inspect the roadmap.
4. Exclude entries whose mapping is stale, colliding or incomplete.
5. Return one primary skill, optional complementary skills, boundaries and
   missing inputs. The workflow controller writes this assignment into its plan.

Reuse an accepted allocation when the lane, requested artifact, input type,
tool, constraints and behavior fingerprints are unchanged. Do not rescan the
whole portfolio for every project step. Rescan or compare candidates when a new
capability appears, a mapping changes, the selected skill fails or the workflow
controller reports a real gap.

## Portfolio maintenance

```bash
python scripts/skill_registry.py scan --no-plugins
python scripts/skill_registry.py report --include-unready
python scripts/skill_registry.py duplicates
python scripts/skill_registry.py validate
python scripts/skill_registry.py package-check
python scripts/skill_audit.py audit --output-md skill-audit.md
```

Edit `registry/skill-roadmap.json` after reading the candidate's full `SKILL.md`
and any behavior-bearing references. Then rerun `scan` and acknowledge the
mapping against its current fingerprint:

```bash
python scripts/skill_registry.py ack-map --skill NAME --review-level full-reviewed
```

Record outcomes only after real use. Keep usage frequency separate from quality
evidence; neither one substitutes for an artifact review.

## Safe upgrades

Never overwrite a locally modified skill with a blind copy. Use
`scripts/skill_transaction.py prepare` for a three-way comparison, resolve all
conflicts in staging, then create a verified backup before activation. Preserve
source commit, license and local modifications in `skill-sources.json`.

For retirement, run `prepare-retire` with usage and dependency evidence first.
Review its plan, then run `retire --approved retire`. The command verifies the
unchanged skill, moves it to a dated archive and records the transaction in
`skill-retirements.json`. Use `restore-retired --approved restore` to reactivate
that verified archive. System and plugin-cache skills are protected.

Read [references/governance.md](references/governance.md) before merging,
disabling or replacing a skill, [references/evolution.md](references/evolution.md)
when recording learning, scoring or retirement evidence, and
[references/registry-schema.md](references/registry-schema.md) when adding routes
or evidence.

Read [references/role-model.md](references/role-model.md) when deciding whether
a change belongs to the skill manager or the workflow controller.
