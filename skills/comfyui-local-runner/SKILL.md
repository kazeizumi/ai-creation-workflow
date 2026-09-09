---
name: comfyui-local-runner
description: Run an existing ComfyUI API-format workflow on a local server from a reproducible JSON manifest. Use after local execution is selected and the exact workflow, input files, overrides, output, and failure fallback are approved.
---

# ComfyUI local runner

This backend submits approved work. It does not start ComfyUI, install nodes,
convert UI-format workflows, or create prompts.

1. Export the workflow with **Save (API Format)** from ComfyUI.
2. Create a manifest using [references/manifest.md](references/manifest.md).
3. Validate it without contacting ComfyUI:

```bash
python scripts/run_local.py local-job.json --dry-run
```

4. Confirm the generation contract in `h3-runtime-router`, then run:

```bash
python scripts/run_local.py local-job.json
```

The runner uploads declared media, patches exact node input fields, submits one
prompt, polls its prompt ID, downloads all output files and writes `run-state.json`.
It only accepts loopback ComfyUI URLs unless `--allow-remote` is explicit.

On a timeout, inspect the saved prompt ID and ComfyUI history before retrying.
Do not create a duplicate paid or long-running job merely because the client
lost its connection.
