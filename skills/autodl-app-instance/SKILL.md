---
name: autodl-app-instance
description: Securely list, inspect, start, discover, and stop AutoDL Art application instances from Windows, macOS, or Linux. Use when a task needs an AutoDL application instance lifecycle or its proxied ComfyUI panel URL; do not use it to submit generation jobs.
---

# AutoDL application instance

Use `scripts/autodl_instance.py` for the instance lifecycle. It calls the official
AutoDL Art application API with TLS verification and never places the developer
token in a child-process command line.

Read [references/api.md](references/api.md) when configuring credentials,
diagnosing an API error, or reviewing the supported endpoints.

## Operating rules

- Resolve one exact instance before powering it on. When a name matches multiple
  instances, show the candidates and let the user select one.
- Treat `boot` as lifecycle setup only. The caller owns shutdown and must use a
  `finally` path or the batch runner in `minimax-h3-cloud`.
- After the instance reaches `running`, discover the proxied panel from the
  current snapshot. Do not reuse an older panel URL after a restart.
- Do not print the token, `root_password`, or `jupyter_token`.
- Do not release or delete instances. This skill intentionally has no release
  command.
- Starting or stopping an instance changes external state. Use the authorization
  already given for the current task; otherwise obtain explicit authorization
  immediately before the action.

## Commands

```powershell
python scripts/autodl_instance.py list
python scripts/autodl_instance.py status --uuid pro-xxxxxxxxxxxx
python scripts/autodl_instance.py snapshot --uuid pro-xxxxxxxxxxxx
python scripts/autodl_instance.py boot --uuid pro-xxxxxxxxxxxx
python scripts/autodl_instance.py off --uuid pro-xxxxxxxxxxxx --wait
```

Machine-readable results go to stdout as JSON. Progress and errors go to stderr.
`boot` returns `instance_uuid` and the current `panel_url`.

On Windows, run `powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1`
for a local dependency and credential check. Add `-Probe` only when a live,
read-only AutoDL instance-list request is wanted.
