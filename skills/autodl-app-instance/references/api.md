# AutoDL application API notes

Authoritative documentation: <https://autodl.art/docs/app_api/>

- API host: `https://www.autodl.art`
- Authentication header: `Authorization: <developer token>` without `Bearer`
- Prefix: `/api/v1/adl_dev/dev/instance/pro`
- Supported operations in this skill: `list`, `status`, `snapshot`, `power_on`,
  and `power_off`
- `power_on` uses `payload: "gpu"` because the API does not support CPU-only
  startup for application instances.

Set `AUTODL_TOKEN` in the process environment, or store this single assignment
in `%USERPROFILE%\.config\autodl.env` on Windows or
`~/.config/autodl.env` elsewhere:

```text
AUTODL_TOKEN=
```

The parser reads the assignment as data; it does not execute the file.
