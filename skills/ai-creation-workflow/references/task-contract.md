# Task contract

Capture these fields before a full workflow starts:

- `objective`: the observable result.
- `deliverables`: exact files, formats and destinations.
- `inputs`: provided materials and their authority.
- `constraints`: duration, aspect ratio, style, identity, language, budget,
  platform and deadlines.
- `locked_decisions`: content that downstream stages may not silently change.
- `acceptance`: evidence that proves each deliverable is usable.
- `outside_scope`: items intentionally left out.
- `runtime_authority`: which external or paid actions are already authorized.
- `context_policy`: compact, standard or expanded; include the concrete reason
  when expanded context is required.
- `delegation`: root by default; record a subagent only for an independent node
  with a bounded packet, separate write scope and observable acceptance.

Use `unknown` for a real unknown. Do not invent a value to make the contract
look complete. Ask only when the unknown blocks the next useful stage.
