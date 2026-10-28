# ADR-0033. Contracts and reviews are Warrant 3 records

Status: PROPOSED; accepted by the owner's re-signature of the manifests and the merge (steps
below). Date: 2026-10-28. Supersedes the tooling of ADR-0024 (`scripts/contract.py`, the contract
files in `docs/contracts/`, unsigned proposal files) and ADR-0032 (the `agent-review` check, its
allowlist). Keeps ADR-0023 (owner-pinned witnesses), ADR-0028 (the agent tier), ADR-0030 (trust
root) and the base-pinned witness gate unchanged in what they decide. Owner decision 2026-10-28:
governance moves onto Warrant 3, deleting machinery, adding no metric.

## Decision

**The store.** `.warrant/records.jsonl` and `.warrant/blobs/` hold this repository's Warrant 3
records (warrant-graph; its specification is V3.md in s0fractal/warrant); `.warrant/v3.json` is the receiver's
trust and profile, `.warrant/merge.json` the review loop's base branch, required checks and owner
paths. Both configuration files are owner-read (`.github/CODEOWNERS`).

**A contract is a lineage.** Each invariant contract is a `sokol-contract@1` lineage: one version per
decision, its body the statement, evidence text, witnesses, the decision (`because`, the hash of the
statement it replaces), and its state: `active` (owner tier), `provisional` (agent tier, ADR-0028) or
`retired` (with the retirement record of ADR-0024, R1-R7 unchanged). A version's record id covers its
whole body and, through `lineage`, the whole history before it. The 80 contracts and their 100
decisions were migrated from Git at `0fec343a` (the commit that added the store carries the
migration script; its `verify` replays it IDENTICAL; the script is then deleted). Tiers are roles in
`.warrant/v3.json`: `contract/owner` (`s0fractal`) accepts `active` and `retired` versions,
`contract/agent` (`agent`) accepts `provisional` ones, `contract/author` (`claude`, `codex`) files
versions.

**Acceptance stays the SSH signature.** The owner's manifest (`docs/witness-manifest.json`, ADR-0023)
pins, besides the witness bodies, closures, build and trust root, each owner-tier contract's leaf
version by record id (`contracts_v2`) and its rendered row (`rows_v2`); the agent's provisional manifest
does the same for its tier. `scripts/witness-pin.py check` reads the lineages from the store with the
standard library alone (the base gate and a counterexample recipient run without Warrant) and refuses
a leaf its tier has not pinned. After a signature, `scripts/contract-store.py carry --actor claude --key …`
files the acceptance it means as an attest by `s0fractal` (`agent`) with the manifest and signature as
blobs, vouched for by a `migration@1` attest of `claude` (`migrator`), so the store's own assessment
agrees; `scripts/contract-store.py check` (CI, with warrant-graph; outside the trust root) assesses the store and re-verifies every
carried acceptance against its SSH signature. The owner's acts per contract change are the same as
before: one re-signature and the merge.

**Rows are rendered.** `docs/INVARIANTS.md` declares that every row comes from its lineage's leaf;
`witness-pin.py regenerate` renders them. A change is a new version filed through the Warrant agent
interface (`warrant_prepare` / `warrant_commit`) with its decision, then `regenerate`, then the tier's
signature.

**Reviews are records.** A pull request's review is a `pr-head@1` lineage (the author's head
versions, each naming the reviewed commit) with `finding@1` records and the `pr/acceptor`'s (Codex's)
acceptance (`python3 -m warrant.review open|head|view`), as in s0fractal/warrant. The Codex review
waker serves this repository from the owner's `~/.warrant/codex-waker/repositories.json` with this
entry (the owner adds it by hand, then re-runs warrant's `integrations/codex-plugin/install.py`, which
installs the warrant-graph the waker runs):

```json
{"repository": "s0fractal/sokol-core", "branch": "main",
 "home": "~/.warrant/codex-waker/sokol-core", "mirror": "~/.warrant/codex-waker/sokol-core/sokol-core.git",
 "trees": "~/.warrant/codex-waker/sokol-core/trees", "checkout": "~/Projects/sokol-core"}
```

(absolute paths in the file: the waker refuses relative ones and shared ones). The owner still merges
every pull request; `.warrant/merge.json` is there for the waker's `due`, not for merging on
acceptance.

**The engine is pinned.** CI installs `warrant-graph==3.0.0a2` and its dependencies with
`--require-hashes` from `.github/warrant-requirements.txt`.

## Deleted

`scripts/contract.py`, `scripts/contract-shadow.py`, `scripts/contract-task.py` (its bounded-input
helpers and contract context moved to `scripts/task_inputs.py` for proof-task, counterexample-task
and sokol-dev), `scripts/check-review.py`, their four test files,
`.github/workflows/agent-review.yml`, `.github/review-allowlist`, the 80 contract files and the
proposals directory of `docs/contracts/`; in `witness-pin.py` the JSON contract loader, per-row
markers, proposals and `trust_root_v1` computation (docs/RETIRED.md, archive tag `archive/2026-10-28`).
`scripts/contract-store.py` (Warrant-level check and `carry`) is new and outside the trust root.

## What is lost

1. **A required check that a review exists.** ADR-0032's `agent-review` job (never made required) is
   gone and nothing replaces it as a GitHub check: the review records are read by the waker and the
   owner, not by a gate, because the owner merges by hand. Merging on acceptance is not adopted.
2. **Reviews by any allowlisted login.** Only actors with a key in `.warrant/v3.json` (claude, codex)
   can file review records; a GitHub review by a person counts for nothing in the store.
3. **Proposal-time checks.** `contract.py propose` refused a proposal against a stale contract hash or
   naming a missing witness when it was filed; now a version is checked when `check` reads the store
   (witnesses against the evidence text, the decision chain, forks) and its witness bodies when they
   are pinned. A filed version that fails is refused at the next check, not at filing.
4. **Unsigned annotations.** A version's id covers its annotations: editing one is a new version that
   waits for its tier's acceptance (#67 GAPS G7). No annotation changed in the history.
5. **The contract-task command line and its reports** (`context`, `run`, `verify --replay`) and
   sokol-dev's `context`, `check` and `verify`: an agent runs a contract's witnesses by name with
   `cargo test` or `python3 scripts/test_*.py`. The unit tests of the report format went with them.
6. **contract-shadow.py's projections** of IPC-A1 to Markdown and bounded JSON.
7. **Re-verification of history from the tree.** The 100 historical acceptances are MIGRATED: vouched
   for by `claude`'s migration attest and by the replay at the commit that added the store, which
   needs Git history; only acceptances carried after the move keep their manifest and signature in
   the store.
8. **Between a signature and `carry`** the store shows the new leaf as PENDING while the manifest pins
   it; `contract-store.py check --every-pin` (a push to main) refuses that state, so carry precedes the merge.
9. **One extra act at this transition**: the base gate runs main's checker, which reads the old
   manifest fields, so the owner signs once with the new checker and once with main's (below).

## The transition (this pull request)

The base gate and CI's pinned-witness step run main's `witness-pin.py` against this tree. Main's
checker finds no contract files, so it treats every row as the owner's and reads the old fields
`rows`, `witnesses`, `closures_v4`, `contracts`, `build_v3`, `trust_root_v1`, `trust_root_v2`; the new
checker reads `rows_v2`, `contracts_v2` and the unchanged `witnesses`, `closures_v4`, `build_v3`,
`trust_root_v2`. Both sets live in one manifest under one signature: each `sign` keeps the fields it
does not compute.

1. The agent re-signs the provisional manifest with the new checker (`sign-provisional`); done in this
   pull request.
2. The owner, in a checkout of this pull request's head:
   `python3 scripts/witness-pin.py sign --key ~/.ssh/sokol_witness_owner`, then
   `git show origin/main:scripts/witness-pin.py > /tmp/witness-pin-main.py &&
   python3 /tmp/witness-pin-main.py --root . sign --key ~/.ssh/sokol_witness_owner`, and commits
   `docs/witness-manifest.json` and its signature. The second signature pins every row in the old
   fields, the five provisional ones included: main's checker cannot tell the tiers apart without
   contract files. Only main's checker reads those fields, for this one merge.
3. The owner merges. A later re-signature with the new checker leaves the old fields as they are.

## Checks

`scripts/test_witness_pin.py` `StoreContracts`: a row edited by hand is refused and `regenerate`
restores it; a new leaf version waits for the owner's signature; a forked lineage is refused; a later
version without its reason is refused; a retired contract drops its row only with the owner's
signature. Each was burned by a mutant of the check it names (in the pull request).
`scripts/test_contract_store.py`: the migrated store passes; a carried owner acceptance whose
signature does not verify is refused, and so is one whose manifest verifies but pins another version
(each burned by a mutant of its check). `scripts/test_task_inputs.py` holds the bounded-input tests that
moved with the helpers.
