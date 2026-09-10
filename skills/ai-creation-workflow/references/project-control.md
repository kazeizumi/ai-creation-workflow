# Project control

Continue an existing project in place. Create a new project only when the work
has its own deliverables and lifecycle. Keep generated binaries separate from
source manifests and creative documents.

The project control file contains:

- outcome and current status;
- authoritative input inventory;
- confirmed decisions and assumptions;
- context tier, current-stage references and the reason for any expansion;
- stage table with primary skill, dependencies, output and validation;
- delegation decisions, bounded input packets and non-overlapping write scopes;
- pending gates and their concrete choices;
- external job IDs and retry state;
- deliverable index and closeout evidence.

On resume, read the control file first, verify any drift-prone external state,
then continue the first `ready` or recoverable `running` stage. Do not recreate
completed work unless its input fingerprint changed.

The authoritative stage states are `pending`, `ready`, `running`, `blocked`,
`review`, `accepted`, `failed`, and `stale`. Validate a persisted state with:

```bash
python scripts/workflow_state.py validate workflow-state.json
```

Use `transition` for a checked state change and `invalidate` with the changed
input key and fingerprint. An unchanged fingerprint is idempotent. Invalidation
marks the named consumer and its dependency descendants, while independent
accepted stages remain valid. Record a declined or approved delegation with the
`delegation` command so the reason, bounded input packet, write scope and
acceptance evidence survive a resume.
