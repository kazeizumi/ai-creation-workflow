---
name: minimax-h3-cloud
description: Run MiniMax H3 or compatible ComfyUI workflows already installed on an AutoDL application instance. Use to list and select remote workflows, inspect their real input slots, upload references, submit a batch, poll by prompt ID, download results, validate files, and shut the instance down.
---

# MiniMax H3 cloud execution

This skill is the execution backend for existing prompts and reference plans. It
does not rewrite scripts, shot design, prompts, or local production rules.

Install its Python dependency with `python -m pip install -r requirements.txt`
in the environment that will run the scripts.

The preferred path is `scripts/run_batch.py`. It starts one approved AutoDL
instance, discovers its current panel, submits the selected installed workflow,
downloads every result, records state, and shuts the instance down in `finally`.

## Required authorization gate

Before starting a stopped instance, confirm the exact instance and the purpose
of the paid boot. Before an actual generation run, also state and confirm the
selected workflow, input files, job count and duration, output directory, and
failure fallback. Listing or inspecting workflows is read-only only after the
panel is already running; it does not itself submit generation work.

## Select an installed workflow

First boot the approved instance with `autodl-app-instance`, then list the
workflows that exist on that instance:

```powershell
python scripts/workflow_tool.py list --base-url $env:SEETACLOUD_BASE_URL
```

Select by exact `workflow_id`; do not infer from a stale name or an older
instance. Inspect the selected workflow and save its current writable inputs:

```powershell
python scripts/workflow_tool.py inspect `
  --base-url $env:SEETACLOUD_BASE_URL `
  --workflow-id "exact-installed-workflow-id" `
  --out workflow-map.json
```

When the instance or workflow changes, inspect it again. The inspection report
shows media loaders and scalar values, but mappings are heuristic: review them
before the first paid submission.

## Batch manifest

Read [references/manifest.md](references/manifest.md) before preparing a batch.
Every job names one exact installed workflow and supplies its actual
`input_values`. Media paths use an explicit `$upload` marker.

Run a batch only after the authorization gate:

```powershell
python scripts/run_batch.py batch.json
```

The runner submits all jobs before polling, associates results only with their
own prompt IDs, streams downloads through `.part` files, runs `ffprobe` when it
is available, and powers the instance off even after an error. Keep-on behavior
must be explicit in both the manifest and the current user instruction.

If the instance is already running, the runner refuses to adopt it by default
because it may contain unrelated jobs. Use `--adopt-running-instance` only after
checking its queue and confirming that this batch may own its shutdown. Use
`--dry-run` to validate paths and the manifest without contacting AutoDL.
