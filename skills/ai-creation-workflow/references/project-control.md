# Project control

Continue an existing project in place. Create a new project only when the work
has its own deliverables and lifecycle. Keep generated binaries separate from
source manifests and creative documents.

The project control file contains:

- outcome and current status;
- authoritative input inventory;
- confirmed decisions and assumptions;
- stage table with primary skill, dependencies, output and validation;
- pending gates and their concrete choices;
- external job IDs and retry state;
- deliverable index and closeout evidence.

On resume, read the control file first, verify any drift-prone external state,
then continue the first `ready` or recoverable `running` stage. Do not recreate
completed work unless its input fingerprint changed.
