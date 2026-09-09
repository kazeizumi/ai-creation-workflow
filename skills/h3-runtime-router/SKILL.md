---
name: h3-runtime-router
description: Select and control MiniMax H3 execution through local ComfyUI or an AutoDL cloud instance. Use after prompts and references are ready, especially when runtime choice, workflow identity, paid-generation authorization, failure recovery, or cost comparison must be resolved.
---

# H3 runtime router

When the user asks to generate H3 video without specifying the runtime, ask one
concise question: **cloud or local?** If the current request already names one,
use it and do not ask again.

## Build the generation contract

Before any real submission, identify and confirm the following for the current
run:

- backend and exact workflow name or file;
- reference files and real upload order;
- prompt and parameter overrides;
- job count and duration;
- output directory;
- timeout, retry and failure fallback;
- cloud shutdown behavior when applicable.

A previous render does not authorize a new render. A confirmed purpose, input,
scope, output and fallback does. Preserve that authorization through retries of
the same job.

## Route execution

- **Local:** use `comfyui-local-runner` with an already running ComfyUI server
  and an API-format workflow JSON.
- **Cloud:** use `autodl-app-instance` to resolve and start the exact instance,
  then `minimax-h3-cloud` to inspect and run an installed workflow by exact ID.

Never infer a cloud workflow from an old display name. Never resubmit merely
because polling failed; recover the existing prompt or job ID first.

## Compare cost

Use `cost = hourly_rate * runtime_minutes / 60`. Compare cost per successful
clip, not only hourly price. Include boot, upload, queue and failure overhead
when measured. Read [references/runtime-selection.md](references/runtime-selection.md)
for the decision rule and [references/cost-benchmark.md](references/cost-benchmark.md)
for an editable example.
