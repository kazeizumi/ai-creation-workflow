# Governance rules

Discovery, installation, routing, quality and retirement are separate decisions.

- **Discovery** proves a skill exists and exposes metadata.
- **Mapping** states capability, stage, role, boundary and overlap.
- **Readiness** checks entry structure, linked files, source metadata and drift.
- **Quality** requires version-bound evidence from actual tasks.
- **Retirement** requires a tested replacement, unique-capability review,
  recoverable backup and explicit authorization for the change.

System and plugin-managed skills are protected from local mutation. Shared
skills may be updated through a staged three-way merge. A duplicate score is a
review signal; it is never automatic permission to delete or merge.

Use a source allowlist and inspect a downloaded skill before activation. Treat
instructions, scripts and tool declarations from outside repositories as
untrusted until reviewed.
