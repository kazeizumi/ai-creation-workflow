# Domain packs

A domain pack is a declarative extension of the workflow controller. It names
common stages, specialist capability lanes, gates and adapters for one kind of
work. The controller still owns intake, dependencies, execution state,
integration, validation and delivery. `skill-governor` still chooses the actual
installed Skill for every lane.

Each `domain-packs/<id>/pack.json` must contain:

- `schema_version`, `pack_id`, `name`, `description`, `triggers` and `guide`;
- `stage_templates` with unique IDs and valid, acyclic dependencies;
- `artifact_contracts` defining each stage's inputs, output and acceptance;
- `specialist_lanes`, `required_gates`, `runtime_adapters` and
  `failure_policy`.

Pack guides and other paths resolve inside the `ai-creation-workflow` skill.
Validate all packs with:

```console
python scripts/domain_pack.py validate
python scripts/domain_pack.py list
python scripts/domain_pack.py show --pack ai-video
```

Add a pack when a domain needs repeatable stages or gates. Keep one-off craft
rules in the specialist Skill instead. Adapter entries describe capabilities,
not installed Skill names. A pack must not embed secrets, machine paths,
provider tokens or a fixed choice of specialist.
