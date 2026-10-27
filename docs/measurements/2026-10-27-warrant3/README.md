# Warrant 3 for sokol-core's governance: phase 0 baseline and phase 1 shadow mirror

Date: 2026-10-27. Source: `main` at `dad26967ae1497c73ca8a11cf7a5c8987c0dc213` (2026-10-21, the
merge of #62). Status: a measurement. Nothing here is read by the gate, CI, `scripts/contract.py`
or the agent-review check; the contracts, the manifests and their signatures stay the only
authority (ADR-0023, ADR-0024, ADR-0028, ADR-0030). No gate, workflow, manifest or signature was
changed, and nothing was signed as the owner or the agent.

The question: can Warrant 3 (`warrant-graph` 3.0.0a1, its spec docs/V3.md in s0fractal/warrant)
carry the governance this repository runs with its own machinery? The plan is in phases with stop
criteria: phase 0 measures, phase 1 builds a read-only mirror and lists what it cannot carry
([GAPS.md](GAPS.md)), and this report ends with the recommendation for phase 2.

## Phase 0: how much of the history is governance

`scripts/governance-baseline.py` counts from Git objects only; its output for the source commit
is `docs/measurements/2026-10-27-warrant3/baseline.json` (same commit, same bytes). The predicates,
exactly as the script states them:

- **Window**: commits reachable from the source whose committer date is at or after
  2026-10-01T00:00:00Z. This history starts on 2026-10-10 (the clean start), so the window is the
  whole history: 230 commits, 154 of them non-merge.
- **Governance paths G**: `docs/contracts/**`, `docs/adr/**`, `scripts/contract*.py`,
  `scripts/witness-pin.py`, the owner and provisional manifests with their signatures,
  `.github/workflows/witness-gate.yml`.
- **(a) Commits**: a non-merge commit touches G when its diff against its parent names a G path.
  It is an INVARIANT change when, for a contract file it changes, the projection {statement,
  evidence_text, witnesses, status, retirement} differs from the parent's (or the file is added or
  removed); otherwise MACHINERY when it touches a G path outside `docs/adr/`; otherwise ADR_ONLY.
  A tier-only change (a promote) is MACHINERY: who stands behind the row changed, not the row.
- **(b) Owner acts per ISO week** (UTC): re-signs = non-merge commits changing the owner
  manifest's signature; agent signs = the same for the provisional one; promotes = contracts
  gaining the decision "promoted by the owner"; merges = merge commits on main's first-parent
  chain (GitHub reports all 60 as merged by the owner's login, s0fractal); owner-path merges = those merges whose
  diff names a path the owner's signature covers (signers file, `scripts/witness-pin.py`, the gate
  workflow, the owner manifest and its signature).
- **(c) Lines**: newline count of the governance code, tests and workflows listed in the script.

### (a) Commits touching governance

| class | commits | of 154 non-merge |
| --- | ---: | ---: |
| touching G | 106 | 69% |
| INVARIANT (a contract's statement, witnesses, evidence or retirement moved) | 27 | 18% |
| MACHINERY | 69 | 45% |
| of which: scripts or workflows | 28 | |
| of which: an unsigned proposal filed | 27 | |
| of which: manifests or signatures only | 13 | |
| of which: decision or tier only (the one promote) | 1 | |
| ADR_ONLY | 10 | 6% |

Two INVARIANT commits also changed governance code. Read the 27 "proposal" commits as the first
half of an invariant change (an agent records an intent; the owner accepts it later in an
INVARIANT commit), not as machinery work: counted that way, invariant work is 54 commits and the
machinery proper (code, workflows, re-pins alone) is 42.

### (b) Owner acts per week

| ISO week | re-signs | agent signs | promotes | merges | owner-path merges |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-W41 (history starts Sat 10-10) | 15 | 0 | 0 | 13 | 9 |
| 2026-W42 | 19 | 6 | 1 | 44 | 27 |
| 2026-W43 | 0 | 0 | 0 | 3 | 0 |
| total | 34 | 6 | 1 | 60 | 36 |

Every merge is an owner act today: 60 merges and 34 manifest signatures between 2026-10-10 and
2026-10-21, the last merge on main. 24 of the 60 merges touched no path the owner's signature covers; those are the ones a
merge rule without the owner could take over (phase 2's question).

### (c) Governance code

| | files | lines at the source | at the history's first commit |
| --- | --- | ---: | ---: |
| code | `scripts/witness-pin.py` 1192, `scripts/contract-task.py` 425, `scripts/contract.py` 324, `scripts/check-review.py` 171, `scripts/contract-shadow.py` 138 | 2250 | 0 |
| tests | `scripts/test_witness_pin.py` 554, `scripts/test_contract_tool.py` 448, `scripts/test_contract_task.py` 395, `scripts/test_check_review.py` 198, `scripts/test_contract_shadow.py` 166, `scripts/test_gate_provenance.py` 145, `scripts/test_trust_root.py` 142 | 2048 | 0 |
| workflows | witness gate 135, agent review 64 | 199 | 0 |

4298 lines of Python and 199 of workflow, all written in this history. 480 lines of
`scripts/witness-pin.py` (its `rust_*`, `py_*` and stripping functions) are the Rust and Python
witness-body and closure extraction: that part is
the domain code no record format replaces ([GAPS.md](GAPS.md) G1, G2).

## Phase 1: the shadow mirror

`scripts/warrant3-mirror.py` builds a Warrant 3 store in `.warrant/` of this branch, the way
warrant's own v2-to-v3 migration did (its spec docs/V3.md, §9): deterministic, every record
`sig: null`, vouched for by one `migration@1` attest of a checker. It runs only under
`warrant-graph` 3.0.0a1 exactly (`scripts/warrant3-mirror.requirements.txt`; it also refuses any
installed package bytes other than that wheel's), Python 3.12 and cryptography 50.0.2, which its
code identity names.

### The mapping

| sokol | Warrant 3 |
| --- | --- |
| a contract file | a `sokol-contract@1` lineage, filed as `sokol-core/files` (the files are unsigned) |
| each entry of its decisions, and the contract before its first decision when it existed then | one version; its content is the contract file as Git holds it after that decision |
| tier: owner row, provisional row, retired row | state `active`, `provisional`, `retired` (with the retirement record and a `replaced_by` reference); guard: one acceptance by the role `contract/owner`, or `contract/agent` for `provisional` |
| the owner's (agent's) SSH signature over a manifest whose contract pin equals the version's | an `attest` by `owner` (`agent`), `verdict: accept`, naming the pin, the manifest's and the signature's sha256 and the commit; from the earliest such signature, verified under the source's signers file |
| a proposal file Git still holds | a blob the version names |
| an ADR file | a `sokol-adr@1` lineage of one version whose `file` is the Markdown as a blob |
| the migration | one `migration@1` attest by the checker `sokol-warrant3-mirror`, whose map lists the Git objects each record came from |

The receiver's profile is `.warrant/mirror.json` (the shape of warrant's `.warrant/v3.json`; named
so that it grants this repository nothing): roles `contract/owner` = `owner`, `contract/agent` =
`agent`, and the mirror checker as `migrator` and sole `schema/author`.

### The store

235 records (100 contract versions, 100 acceptances, 32 ADRs, 2 schemas, the migration), 94 blobs
(32 ADRs, 61 proposals, the map), 832 KB; two runs give the same bytes. Under its profile:
0 problems, 0 rejected, 232 records MIGRATED and 3 SIGNED; 75 `active` and 5 `provisional`
contract lineages and 32 ADR lineages, all ELIGIBLE; 100 contract versions MET (94 by the owner,
6 by the agent: one acceptance per version, from 27 distinct signing commits), 32 ADR versions
with no guard. Every version found a verified signature: none is left without an acceptance, and
no signature in the history failed to verify.

### Verify: IDENTICAL

`warrant3-mirror.py verify` replays the migration from the source commit the genesis names and
then re-derives everything from the store's records alone:

| check | result |
| --- | --- |
| replay of the migrated record ids | IDENTICAL, 232 of 232 |
| each contract file re-derived from its lineage's leaf | IDENTICAL, 80 of 80 files, byte for byte |
| each historical version re-derived from its path | 100 of 100: 99 byte for byte, 1 equal as JSON only (residual R1) |
| INVARIANTS.md rows, rendered by `scripts/witness-pin.py`'s own row function | IDENTICAL, 80 rows (as a set; residual R2) |
| ADR files from their blobs | IDENTICAL, 32 of 32 |
| every leaf effective, ELIGIBLE and accepted by its tier's signer | yes, 80 of 80 |

`warrant3-mirror.py selftest`: the mirror's pin equals `scripts/witness-pin.py`'s contract pins
for all 80 contracts; a synthetic contract that is changed, made provisional, promoted and retired
(no contract is retired on main, so this is the only exercise of retirement) round-trips at every
version; a broken previous-statement chain is refused; and five mutants of the store (an edited
statement, a dropped leaf acceptance, a dropped ADR, a broken migration signature, a dropped later
version) are each caught by the check they name, after the unmutated store verifies IDENTICAL.
The selftest was itself burned: a verify that never reports an unaccepted leaf fails M2.

### Residuals

- **R1.** IPC-A1's first version (commit `cb0904d8`) was written before `scripts/contract.py`'s
  byte format (another key order); it equals the re-derived contract as JSON, and verify lists it
  apart instead of hiding it.
- **R2.** The prose of INVARIANTS.md and the order of its rows are the document's, not the
  contracts'; the rows are compared as a set of exact lines.
- **R3.** 6 of the 67 proposals no longer exist in Git (`scripts/contract.py` deletes a proposal
  when it is accepted); their sha256 stays in the decision, and the version carries no blob.
- **R4.** The witness, closure, build and trust-root pins of each manifest are carried only as the
  manifest's sha256 in each acceptance ([GAPS.md](GAPS.md) G1).
- **R5.** The acceptances are MIGRATED, not SIGNED: the store holds the fact that an SSH signature
  verified, not the signature; only a replay from Git re-checks it (G4).
- **R6.** The schemas are authored by the mirror checker alone, at quorum 1, and the mirror's key
  is the session's own (seed outside the repository). A receiver that adopts the store would set
  its own schema authors and quorum.

## Recommendation: proceed to phase 2, as a shadow, with stop criteria

Phase 1 found no gap in the record layer: every contract, version, acceptance, tier and ADR maps
to Warrant 3 natively and comes back byte for byte. Warrant 3 even keeps what sokol loses (R3: a
proposal is a pending version, not a file deleted on acceptance). The gaps are all in the
machinery around the records ([GAPS.md](GAPS.md)): witness-body pins (G1), the Rust runner (G2),
the base-pinned witness gate (G3) and the owner's SSH signature (G4). Sokol keeps those four; none
of them is phase 2's subject, and none should move before warrant gains the features GAPS proposes.

Phase 2 (pull request reviews as Warrant records, in place of ADR-0032's comment records) is where
Warrant is strongest and the current approach is stuck: ADR-0032 is PROPOSED and waits for the
owner's ruleset change and a second GitHub login, because a review counts by login. In Warrant a
review counts by the reviewer's key and role, so no second login is needed, the review is bound
to a head by record id, and findings become challenges. Proceed, as a shadow first:

- **Preconditions** (warrant changes, GAPS W-5 and W-6): the review waker takes its repository and
  branch from configuration; the review loop and the gate are installable for another repository
  (or vendored at an exact commit with their code identity).
- **Shape**: review records in each pull request's `.warrant/` beside the agent-review check;
  no required check changes until the shadow has run; no change to the witness gate, manifests or
  signatures; nothing during RC-1 that needs a workflow change.
- **Stop criteria**, measured on the first ten pull requests reviewed in shadow: stop if the
  Warrant verdict on a head and the agent-review check's verdict differ for any reason other than
  who may review; stop if any pull request needs an owner act it does not need today (baseline
  above: one merge per pull request, one re-sign per pinned change); stop at signed verdicts only
  if no finding could be replayed (G2: Rust findings stay unreplayed theses until W-2); stop if
  the waker cannot serve this repository without warrant changes beyond W-5 and W-6.
- **What phase 2 can save**: the 24 of 60 merges that touched no owner-signed path are the
  candidates for merge on acceptance (warrant's gate) in a later phase; re-signs and owner-path
  merges stay the owner's.

## Reproduce

```shell
uv venv --python 3.12 VENV && uv pip install --python VENV/bin/python -r scripts/warrant3-mirror.requirements.txt
python3 scripts/governance-baseline.py --source dad26967ae1497c73ca8a11cf7a5c8987c0dc213
VENV/bin/python scripts/warrant3-mirror.py verify     # needs no key; replays from Git
VENV/bin/python scripts/warrant3-mirror.py selftest
```

`warrant3-mirror.py run` rewrites `.warrant/` and needs the mirror checker's seed (outside the
repository). Any edit of the mirror script or of `scripts/witness-pin.py` changes the mirror's
code identity: the store must then be rebuilt, and verify refuses a genesis naming other code.
