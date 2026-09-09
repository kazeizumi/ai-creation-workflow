---
name: skill-governor
description: Govern an agent skill portfolio by discovering installed skills, mapping capabilities and boundaries, reviewing overlaps, recording provenance and task evidence, auditing readiness, and preparing reversible upgrades. Use when skills are missing, duplicated, stale, newly installed, being evaluated, or selected for a multi-stage workflow.
---

# Skill governor

Route by capability, stage and boundary. Do not choose a skill because its name
happens to contain a prompt keyword.

## Normal routing

1. Identify the requested functional lane and production stage.
2. Run `scripts/skill_registry.py report --lane "<lane>"` or inspect the roadmap.
3. Exclude entries whose mapping is stale, colliding or incomplete.
4. Prefer one primary skill. Add a complementary skill only for a distinct
   output or validator duty.
5. State the boundary when two candidates overlap.

## Portfolio maintenance

```bash
python scripts/skill_registry.py scan --no-plugins
python scripts/skill_registry.py report --include-unready
python scripts/skill_registry.py duplicates
python scripts/skill_registry.py validate
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

Read [references/governance.md](references/governance.md) before merging,
disabling or replacing a skill, and [references/registry-schema.md](references/registry-schema.md)
when adding routes or evidence.
