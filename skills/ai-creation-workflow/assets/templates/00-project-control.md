# Project control

## Contract

- Objective:
- Deliverables:
- Authoritative inputs:
- Constraints:
- Locked decisions:
- Acceptance evidence:
- Outside scope:
- Runtime authority:

## Context budget

- Token policy: on
- Context tier: compact | standard | expanded
- Canonical contract: this file
- Current-stage packet:
- Expansion reason:
- Reusable routing decision:

## Plan status

- Status: draft | ready | executing | blocked | completed
- Current stage:
- Next consequential gate:
- Existing authorization scope:

## Stage graph

Stage status contract: `pending | ready | running | blocked | review | accepted | failed | stale`.
`stale` means an accepted or in-progress stage consumed a changed input; only
that stage and its real dependants are invalidated.

| ID | Stage | Primary skill | Depends on | Output | Validation | Status |
|---|---|---|---|---|---|---|
| S01 | | | | | | pending |

## Delegation

| Node | Owner | Why delegation saves work | Input packet | Write scope | Acceptance | Status |
|---|---|---|---|---|---|---|
| | root | | | | | not_evaluated |

## Gates

| Gate | Concrete decision | Impact | Evidence ready | Status |
|---|---|---|---|---|

## External jobs

| Backend | Job or prompt ID | State file | Output | Recovery action |
|---|---|---|---|---|

## Deliverables and closeout

| Deliverable | Path | Validation | Result |
|---|---|---|---|
