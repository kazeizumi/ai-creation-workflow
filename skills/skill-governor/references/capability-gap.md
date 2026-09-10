# Capability gap and candidate adoption

Use this branch only when the current task has no accepted route, a selected
Skill fails, candidates compete, or the user supplies a Skill to install or
learn from. The goal is stronger coverage, not a larger library.

## Artifact sequence

1. Copy `assets/templates/capability-request.json` and describe the current
   deliverable, semantic lane, stage, inputs, tools, constraints, acceptance and
   permissions. Add `provided_candidate` when the user supplied a name, path,
   archive or URL.
2. Run `capability_gap.py assess`. Reuse its decision while the request
   fingerprint and mapped Skill fingerprints remain current.
   If the installed registry is empty, stop at `local_scan_required` and run
   `skill_registry.py scan`; a packaged roadmap entry does not prove that the
   Skill is installed.
3. Run `capability_gap.py resolve`. A fit skips the network. A user-provided
   candidate skips discovery but still enters duplicate, gain, license, safety,
   dependency and permission review. A real gap may query GitHub metadata; this
   does not download or install the result.
   When no candidate survives, `gap-resolution.json` carries the narrow gap
   specification and selects `improve` for a partial existing route, `create`
   for reusable/non-obvious capability, or `use-tool` for a one-off mechanical
   task. Override with `--gap-action` only when the semantic review has stronger
   evidence.
4. For a final candidate, complete
   `assets/templates/candidate-review.json` from the candidate's full Skill and
   only the overlapping installed primary Skill. Run `capability_gap.py adopt`.

## Adoption decision

- `full_install`: a distinct trigger, input/output or tool boundary with a
  measurable unique gain. Stage it, test it against the same request, then
  activate it as `probation`; do not make it the primary route automatically.
- `reference_strengthen`: substantial overlap but a useful licensed method,
  validator or reference. Extract only decision-changing material, preserve
  attribution, update the existing Skill through backup and three-way review,
  and do not create a duplicate Skill directory.
- `reject`: no measurable gain, or unacceptable source, license, safety,
  dependency, permission or maintenance cost.

If the user already chose full installation or reference strengthening, pass
that choice and do not ask again. Otherwise show the decision card and ask once:
"完整安装，还是参考后补强现有功能？" A requested choice never bypasses a
failed or unknown license/safety gate.

## Commands

```bash
python scripts/capability_gap.py assess --request capability-request.json --output routing-decision.json
python scripts/capability_gap.py resolve --request capability-request.json --decision routing-decision.json --output gap-resolution.json
python scripts/capability_gap.py adopt --review candidate-review.json --output candidate-adoption.json
python scripts/capability_gap.py adopt --review candidate-review.json --choice reference_strengthen --output candidate-adoption.json
```

The GitHub adapter retrieves at most five repository metadata results and marks
them untrusted. Inspect only the final one to three behavior-bearing candidates.
Record rejected duplicates so an unchanged request does not trigger another
deep review.

The adapter follows the public [GitHub REST search API](https://docs.github.com/en/rest/search/search)
and accepts `GITHUB_TOKEN` only from the process environment. Repository license
metadata is a first-pass signal: GitHub documents that its license detection
does not cover dependency licenses or every place a project may declare terms.
Confirm the actual candidate and dependency licenses before either adoption
mode. See the [GitHub license API notes](https://docs.github.com/en/rest/licenses/licenses).
