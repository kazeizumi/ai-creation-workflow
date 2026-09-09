# Batch manifest

Use UTF-8 JSON. Paths may be absolute or relative to the manifest file.

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
      "workflow_id": "exact ID returned by workflow_tool.py list",
      "output": "results/G01.mp4",
      "input_values": {
        "664:prompt": "self-contained H3 prompt",
        "132:value": 10,
        "665:自定义宽": 1920,
        "665:自定义高": 1088,
        "137:image": {"$upload": "refs/Picture_01.png"}
      }
    }
  ]
}
```

Rules:

- Copy input keys from the inspection report for the chosen installed workflow.
- Supply prompt, duration, dimensions, sampler settings, LoRA, and media only
  when those inputs exist in the selected workflow.
- `$upload` values are uploaded before submission and replaced with the remote
  filename returned by the panel.
- Set every unused media loader deliberately if the installed workflow contains
  default media that could affect generation. Use neutral placeholders only
  after verifying the workflow expects them.
- Output paths must be unique. Existing outputs are preserved and cause the job
  to stop unless `overwrite_outputs` is set to `true` for the batch.
- `keep_on: true` is honored only when the user also explicitly asks to keep the
  instance running in the current request.
