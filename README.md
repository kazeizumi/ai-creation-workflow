# AI Creation Workflow

[中文说明](README.zh-CN.md)

A portable control plane for AI creative production. It manages the skill
portfolio, turns a creative goal into an auditable project workflow, routes each
stage to a specialist skill, and runs MiniMax H3 through local ComfyUI or an
AutoDL cloud instance.

## What is included

| Skill | Responsibility |
|---|---|
| `ai-creation-workflow` | Project setup, requirement contract, stage graph, gates, state, validation and closeout |
| `skill-governor` | Skill discovery, routing registry, provenance, overlap review, evidence and reversible upgrades |
| `h3-runtime-router` | Local/cloud decision, generation authorization, cost estimate and backend handoff |
| `comfyui-local-runner` | Manifest-driven submission to an existing local ComfyUI API workflow |
| `minimax-h3-cloud` | Exact installed-workflow inspection, upload, batch submission, download and shutdown |
| `autodl-app-instance` | Secure AutoDL application-instance lifecycle and panel discovery |

Creative skills such as screenwriting, directing, prompt writing, VFX and sound
design remain plug-ins. Register whichever implementations you trust; the
orchestrator selects them by capability and stage instead of hard-coding names.

## Install

Python 3.11 or newer is recommended. Preview the installation first:

```bash
python scripts/install.py --dry-run
python scripts/install.py --yes
```

The default target is `~/.agents/skills`. Select individual skills with repeated
`--skill` flags or choose another directory with `--target`.

For AutoDL support:

```bash
python -m pip install -r skills/minimax-h3-cloud/requirements.txt
```

Copy `.env.example` to `.env`, add `AUTODL_TOKEN`, and keep that file local.

## Start a project

Invoke `$ai-creation-workflow` with a goal. It creates a project control file,
records deliverables and constraints, maps stages to installed skills, and stops
only at gates that require a creative choice, paid execution or an irreversible
external action.

For H3, a request without a runtime choice asks one question: **cloud or local?**
After the choice, the runtime router collects the exact workflow, inputs,
duration, output and failure fallback before generation. Use an installed cloud
workflow by exact workflow ID; local execution expects a ComfyUI API-format JSON.

See [`examples/minimal-project`](examples/minimal-project) for a project state
and H3 manifest without private media.

## Verify

```bash
python scripts/verify_release.py
python skills/skill-governor/scripts/test_skill_governor.py
python skills/comfyui-local-runner/scripts/run_local.py examples/minimal-project/local-h3-job.json --dry-run
python skills/minimax-h3-cloud/scripts/run_batch.py examples/minimal-project/cloud-h3-batch.json --dry-run
```

Dry runs do not start instances or submit generation jobs.

## Publishing boundaries

This repository ships orchestration and adapters. Model weights, third-party
workflows, custom nodes and commercial media are separate dependencies. Verify
their licenses before redistributing them.
