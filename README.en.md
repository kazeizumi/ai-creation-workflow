# AI creation workflow: from skill management to H3 renders

[中文主文档](README.md)

Making an AI video gets messy long before the final render. The script is in one
folder, reference images are somewhere else, and nobody remembers which prompt
version produced the clip. A local GPU may run out of memory halfway through,
while a cloud retry can quietly create another paid job. Installing more skills
helps, but it also creates a new problem: deciding which one should handle each
step.

This repository packages the working method used to keep those pieces together.
It records what the project must deliver, where the work currently stands, which
skill owns the next stage, and what still needs approval before a real render.
MiniMax H3 jobs can run through local ComfyUI or through a workflow that is
already installed on an AutoDL instance.

You can use the whole process for a production, or take only the part you need:
skill cleanup, a repeatable local ComfyUI job, or a cloud H3 batch. Writing,
direction, prompting, VFX, and sound stay with their specialist skills. This
repository keeps their inputs and outputs connected.

Jump to the part that matches your job:

- Start with [installation](#install) if this is your first time here.
- Use [`ai-creation-workflow`](#1-project-orchestration-with-ai-creation-workflow) for a complete project.
- Use [`skill-governor`](#2-skill-governance-with-skill-governor) to sort out a growing skill library.
- Use [`h3-runtime-router`](#3-h3-runtime-selection-with-h3-runtime-router) when H3 materials are ready.
- Follow the [local runner](#4-local-execution-with-comfyui-local-runner) for your own ComfyUI machine.
- Follow the [cloud runner](#6-cloud-h3-execution-with-minimax-h3-cloud) for an AutoDL instance.

![How one AI creation project moves through the workflow](docs/images/system-architecture.svg)

## What is included

Two roles lead the package:

| Lead role | Owns | Does not own |
|---|---|---|
| `skill-governor` | The skill library: discovery, registration, allocation, overlap review, evidence, upgrades, backups, and rollback | A project's plan, progress, or specialist craft output |
| `ai-creation-workflow` | The project goal, execution plan, detailed steps, dependencies, gates, progress, validation, and delivery | Mutating the skill library or inventing a specialist's craft method |

When the workflow controller creates or changes a stage, it sends the governor
the requested output, available inputs, tool, constraints, and acceptance test.
The governor returns the best primary skill, any necessary specialist, its
boundary, and missing inputs. The workflow controller writes that assignment
into the plan and carries it through execution.

The following four skills support individual execution stages:

| Execution support | Responsibility | Typical use |
|---|---|---|
| `h3-runtime-router` | Local/cloud choice, generation contract, cost, and failure policy | H3 materials are ready for rendering |
| `comfyui-local-runner` | Manifest-driven submission to an existing local ComfyUI API workflow | Local models and workflow are installed |
| `minimax-h3-cloud` | Installed-workflow inspection, upload, batch submission, download, and shutdown | Running H3 on an AutoDL instance |
| `autodl-app-instance` | AutoDL instance lifecycle and current panel discovery | Starting and stopping the cloud backend |

AI video is one domain pack inside the workflow controller. Screenwriting,
direction, prompting, VFX, TTS, and sound skills join the stages they own; H3 is
one execution route among them.

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

Set `AUTODL_TOKEN` in the process environment or in `~/.config/autodl.env`.
Keep real credentials outside the repository.

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

## 1. Project orchestration with `ai-creation-workflow`

Use this controller for the project plan and execution when two or more stages
depend on each other, or when the work includes paid generation, batches,
handoffs, or long-running state. At each stage it asks `skill-governor` for the
best installed specialist, then owns the run, gate, validation, and delivery.

Example invocation:

```text
Use $ai-creation-workflow to produce a 16:9 narrative AI short from this locked
script. Deliver the shot plan, bilingual H3 prompts, real reference upload order,
rendered media, and validation evidence.
```

The orchestrator selects the smallest control mode:

| Mode | When to use it | State handling |
|---|---|---|
| Direct | One clear, reversible task | Invoke the known specialist directly |
| Light | Two to four dependent stages | Keep a short contract and checkpoints in the session |
| Full | Cross-stage, paid, batched, resumable work | Use the project-control and JSON-state templates |

Full mode starts with:

```text
templates/00-project-control.md
templates/workflow-state.json
```

The project contract records the objective, exact deliverables, authoritative
inputs, constraints, locked decisions, acceptance evidence, excluded scope, and
existing authorization. Each stage declares one primary skill, dependencies,
an output contract, validation, and a retry rule.

Stage states are `pending`, `ready`, `running`, `blocked`, `review`, `accepted`,
and `failed`. If an upstream locked decision changes, mark affected downstream
stages stale before rerunning them.

The default AI-video graph is:

```text
brief → script → content units → story shots → generation segments
→ reference plan and upload order → bilingual prompts → runtime selection
→ render → media QA → edit and sound → delivery
```

A generation segment must define its own opening state, transition, and ending
state. It must not rely on a video model remembering a previous request.

## 2. Skill governance with `skill-governor`

![Skill governance lifecycle](docs/images/skill-governance-cycle.svg)

Use this skill after installing capabilities, when multiple skills overlap, when
an upstream version changes, or when you need evidence for keeping, comparing,
updating, merging, or retiring a skill.

### Discover and route skills

```bash
python skills/skill-governor/scripts/skill_registry.py scan
python skills/skill-governor/scripts/skill_registry.py report --include-unready
python skills/skill-governor/scripts/skill_registry.py report --lane video-runtime
python skills/skill-governor/scripts/skill_registry.py duplicates
python skills/skill-governor/scripts/skill_registry.py validate
```

The default scan covers shared skills in `~/.agents/skills`, protected system
skills in `~/.codex/skills/.system`, and skills exposed by enabled Codex plugins.

`registry/skill-roadmap.json` is human-maintained. A route records the functional
lane, production stage, capability summary, positive trigger, boundary, role,
review level, and declared overlap groups. The included roadmap covers the six
skills in this repository; merge it with your own routing data before scanning
a larger existing library.

After fully reviewing a skill, bind the route to its current behavior fingerprint:

```bash
python skills/skill-governor/scripts/skill_registry.py ack-map \
  --skill h3-runtime-router \
  --review-level full-reviewed
```

### Learn, score, and evolve the portfolio

A newly installed skill starts in `probation`. The governor limits it to a
defined scenario and compares it with the current primary skill on the same
real request. Promotion requires evidence from that comparison; a bundled demo
or marketing description is not enough.

Usage and quality are separate signals. Usage tells us whether a skill was
selected, completed, partially completed, failed, or replaced. It does not prove
quality. Quality evidence must be attributable to the current skill and bound to
the task ID and behavior fingerprint. Score these seven dimensions from 1 to 5:
`fit`, `output`, `reliability`, `efficiency`, `maintainability`, `uniqueness`,
and `safety`.

Record a quality result only after explicit user feedback, an independent
regression, or a measurable change:

```bash
python skills/skill-governor/scripts/skill_registry.py record-outcome \
  --skill h3-runtime-router \
  --task-id project-001-G01 \
  --fit 5 --output 5 --reliability 4 --efficiency 4 \
  --maintainability 5 --uniqueness 4 --safety 5 \
  --verdict pass \
  --source user \
  --evidence "Produced a usable local/cloud decision and generation contract" \
  --artifact artifacts/project-001/runtime-contract.md
```

The audit can return `keep-core`, `keep-specialist`, `trial-review`, `observe`,
`compare`, `repair`, `quarantine-review`, or `protected`. An update keeps the
old evidence as history but sends the new version back to probation.

### Record use and audit the portfolio

```bash
python skills/skill-governor/scripts/skill_audit.py record-use \
  --skill h3-runtime-router \
  --task-id project-001-G01 \
  --result completed \
  --reason "Produced the runtime decision and complete generation contract"

python skills/skill-governor/scripts/skill_audit.py audit \
  --output-json skill-audit.json \
  --output-md skill-audit.md
```

Usage frequency and quality evidence are stored separately. An overlap score is
a review signal and never causes automatic deletion. The full lifecycle rules
are in [`skills/skill-governor/references/evolution.md`](skills/skill-governor/references/evolution.md).

### Retirement gate

The governor proposes retirement only after a tested replacement exists, unique
capabilities have been migrated or judged unnecessary, same-task A/B is no
worse, recent use and project dependencies are checked, the license permits the
integration, and a dated recoverable backup exists. Moving, disabling, merging,
or deleting still requires explicit user approval. The default action is a
dated archive recorded in `registry/skill-retirements.json`, never permanent
automatic deletion.

### Update safely

Use `skill_transaction.py` for a three-way comparison between the installed
baseline, current local version, and new upstream version. Resolve conflicts in
staging, create and verify a backup, then activate. Available operations are:

```bash
python skills/skill-governor/scripts/skill_transaction.py prepare --help
python skills/skill-governor/scripts/skill_transaction.py backup --help
python skills/skill-governor/scripts/skill_transaction.py activate --help
python skills/skill-governor/scripts/skill_transaction.py rollback --help
```

System and plugin-managed skills remain protected from local mutation.

## 3. H3 runtime selection with `h3-runtime-router`

![MiniMax H3 local and cloud flow](docs/images/h3-runtime-flow.svg)

Use this after prompts and references are ready. If a generation request does
not name a runtime, the router asks one question: **cloud or local?** It does not
ask again after the request supplies that choice.

Before a real submission, complete
[`templates/h3-generation-contract.md`](templates/h3-generation-contract.md):

- backend and exact workflow file, name, or ID;
- prompt files, references, and real upload order;
- job count, duration, resolution, and material generation parameters;
- output directory and acceptance evidence;
- expected cost, timeout, retry, and failure fallback;
- cloud shutdown policy and current authorization.

Prompt approval is not generation approval. A timeout is not evidence that the
job failed: recover the existing prompt or external job ID before resubmitting.

The direct cost formula is:

```text
cost per clip = hourly instance rate × occupied minutes / 60
```

Compare end-to-end time per successful clip, including boot, upload, queue,
retry, and shutdown overhead.

## 4. Local execution with `comfyui-local-runner`

Use this backend when ComfyUI is already running and the required models, custom
nodes, and workflow are installed. Export the workflow with **Save (API Format)**.
The runner does not start ComfyUI, install dependencies, convert UI-format
workflows, or author prompts.

A local manifest maps exact `node_id:input_name` keys:

```json
{
  "schema_version": 1,
  "base_url": "http://127.0.0.1:8188",
  "workflow": "workflow_api.json",
  "output_dir": "results",
  "poll_seconds": 5,
  "timeout_seconds": 7200,
  "input_values": {
    "28:prompt": {"$text_file": "Prompt_EN.txt"},
    "27:value": 10,
    "29:megapixels": 0.6,
    "54:value": 1.5,
    "66:image": {"$upload": "Picture_01.png"}
  }
}
```

`$text_file` loads UTF-8 text, `$upload` uploads a local file before submission,
and normal JSON values directly replace workflow inputs.

Validate first:

```bash
python skills/comfyui-local-runner/scripts/run_local.py path/to/local-job.json --dry-run
```

Run only after the generation contract is approved:

```bash
python skills/comfyui-local-runner/scripts/run_local.py path/to/local-job.json
```

The runner uploads inputs, patches the API workflow, submits once, polls by
`prompt_id`, downloads every output, and writes `run-state.json`. It accepts only
loopback URLs by default; use `--allow-remote` only for an explicitly approved
remote ComfyUI server.

## 5. AutoDL lifecycle with `autodl-app-instance`

The client reads `AUTODL_TOKEN` from the process environment or from:

```text
Windows: %USERPROFILE%\.config\autodl.env
macOS/Linux: ~/.config/autodl.env
```

The file contains one local assignment:

```text
AUTODL_TOKEN=replace-with-your-local-token
```

Use `AUTODL_ENV_FILE` to select another local credentials file. Do not put the
token in Git, JSON manifests, or command-line arguments.

Windows diagnostics:

```powershell
powershell -ExecutionPolicy Bypass -File skills/autodl-app-instance/scripts/doctor.ps1
powershell -ExecutionPolicy Bypass -File skills/autodl-app-instance/scripts/doctor.ps1 -Probe
```

The second command adds a read-only instance-list API probe.

Lifecycle commands:

```bash
python skills/autodl-app-instance/scripts/autodl_instance.py list
python skills/autodl-app-instance/scripts/autodl_instance.py status --uuid pro-xxxxxxxxxxxx
python skills/autodl-app-instance/scripts/autodl_instance.py snapshot --uuid pro-xxxxxxxxxxxx
python skills/autodl-app-instance/scripts/autodl_instance.py boot --uuid pro-xxxxxxxxxxxx
python skills/autodl-app-instance/scripts/autodl_instance.py off --uuid pro-xxxxxxxxxxxx --wait
```

`boot` waits for the instance and discovers a current panel URL from the latest
snapshot. Do not reuse a panel URL after a restart. This adapter cannot release
or delete an instance.

## 6. Cloud H3 execution with `minimax-h3-cloud`

For initial workflow discovery, boot the approved instance and use the current
panel URL:

```powershell
python skills/autodl-app-instance/scripts/autodl_instance.py boot --uuid pro-xxxxxxxxxxxx
$env:SEETACLOUD_BASE_URL = "https://current-panel-url"

python skills/minimax-h3-cloud/scripts/workflow_tool.py list `
  --base-url $env:SEETACLOUD_BASE_URL

python skills/minimax-h3-cloud/scripts/workflow_tool.py inspect `
  --base-url $env:SEETACLOUD_BASE_URL `
  --workflow-id "exact-installed-workflow-id" `
  --out workflow-map.json
```

If discovery is the only task, shut the instance down afterward. Reinspect when
the instance or workflow changes.

Create a batch manifest with the exact inspected input keys:

```json
{
  "instance_uuid": "pro-xxxxxxxxxxxx",
  "keep_on": false,
  "poll_timeout_seconds": 3600,
  "max_parallel_polls": 3,
  "state_file": "batch-state.json",
  "jobs": [
    {
      "name": "G01",
      "workflow_id": "exact-installed-workflow-id",
      "output": "results/G01.mp4",
      "input_values": {
        "664:prompt": "self-contained H3 prompt",
        "132:value": 10,
        "29:megapixels": 0.6,
        "54:value": 1.5,
        "137:image": {"$upload": "refs/Picture_01.png"}
      }
    }
  ]
}
```

Validate and run:

```bash
python skills/minimax-h3-cloud/scripts/run_batch.py path/to/batch.json --dry-run
python skills/minimax-h3-cloud/scripts/run_batch.py path/to/batch.json
```

The batch runner starts the exact instance, rediscovers the panel, uploads
declared files, submits the batch before polling, associates results by prompt
ID, streams downloads through `.part` files, uses `ffprobe` when available, and
shuts down in `finally`.

An already-running instance is rejected by default because it may contain
unrelated jobs. Inspect its queue before explicitly using
`--adopt-running-instance`. Honor `keep_on: true` only when the current user
request also authorizes `--allow-keep-on`.

## Approval, recovery, and validation

Require a concrete current scope before paid startup, real ComfyUI submission,
external publication, irreversible skill replacement, or a change to locked
creative content. A real generation names the workflow, inputs, duration or
batch scope, output, and failure fallback; cloud execution also names the
instance and shutdown behavior.

Validate the artifact rather than relying on a command exit code. For video,
inspect duration, dimensions, frame rate, codec, audio streams, visible content,
and the creative acceptance criteria. A shot plan or prompt review proves only
that the materials are ready.

## Repository layout

```text
skills/                      Six independently installable skills
templates/                   Project state and generation-contract templates
examples/minimal-project/    Offline dry-run examples without private media
scripts/install.py           Installer with backups
scripts/verify_release.py    Release and secret hygiene checks
docs/images/                 Bilingual explanatory diagrams
```

## Publishing boundaries

This repository ships orchestration and adapters. Model weights, third-party
workflows, custom nodes and commercial media are separate dependencies. Verify
their licenses before redistributing them.
