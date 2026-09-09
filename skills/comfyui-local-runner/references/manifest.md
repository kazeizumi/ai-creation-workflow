# Local runner manifest

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

Paths are relative to the manifest. Each key is `node_id:input_name` and must
match an existing workflow node and input. `$text_file` loads UTF-8 text.
`$upload` uploads a local file through `/upload/image` and patches the input
with the returned ComfyUI filename. Plain JSON values are written directly.

The workflow must be API format: a JSON object whose node keys each contain an
`inputs` object. UI-format graphs are rejected during dry-run.
