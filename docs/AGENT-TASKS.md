# Agent tasks: contracts and proofs

## One entry point

`python3 scripts/sokol-dev.py next` shows current signature correspondence, provisional
owner-action candidates and the fixed challenge catalog. `inventory` and `map` project
the same contracts and declared witness locations; the map is not a compiler call graph.
`challenge genesis` runs the existing
calibrated Kani method, including its deliberate fault. These are explicit executions.

No text in a contract's annotations, a map or an imported report becomes a recipe.
Essential inventory/map output above 64 KiB is refused; select a contract instead.
An inventory MATCH never establishes execution, semantic adequacy or deployment authority.
The detailed owners and limits below apply unchanged.

A contract is a lineage in `.warrant/records.jsonl` (ADR-0033); its row in
[INVARIANTS.md](INVARIANTS.md) names its witnesses. Run them by name: Rust witnesses as a
`cargo test --release --locked` filter (Linux), Python ones as unittest cases of their test file. `scripts/task_inputs.py` `prepare` gives a contract's bounded context
packet: the leaf version, the witnesses' bodies and whether they and the leaf match the owner's
pins (`MATCH`) or not (`UNPINNED`); it leaves execution `UNKNOWN`. A counterexample to a contract is
a Warrant 3 record (a `finding@1` against a review head, or a new version of the lineage whose
decision names it, ADR-0033); the portable counterexample exchange that carried such packets
between repositories is retired ([RETIRED.md](RETIRED.md)).

## Snapshot and limits

The snapshot records SHA256 and executable bits of the tracked live checkout, including helpers and fixtures; this catches
more drift than owner-pinned witness bodies. It is a conservative input inventory, not a
proven dependency closure. Untracked/generated files, other environment variables, external
binaries, compiler dependencies and remote state remain outside it. The copy has a synthetic
Git index and no original commit history; production build identity is not established. The configuration records
system, architecture and digests of the explicitly listed environment entries. A passing
witness means its compiler-listed matches ran in this configuration, not that every
conditional compilation of its body or every possible topology was exercised.

Inputs refuse symlinks, files larger than 2 MiB, more than 4,096 tracked paths, or over 128 MiB
in aggregate. Verifier output is capped at 1 MiB and execution at 900 seconds; refusal signals
the local process group with SIGKILL and reaps the direct child. Children that start a separate session are outside that
cancellation mechanism. These limits bound retained input/output, not peak RSS or kernel
work. Oversized essential packets are refused, never silently trimmed. Reports and logs stay
outside the checkout to avoid a self-referential snapshot.

Owner signature validity is relative to the supplied signer file. By default its provenance
is `LOCAL_CHECKOUT`; for a separately trusted file, put `--signers /path/to/signers` before the
subcommand. The tool does not discover authority independently or accept/sign any proposal.
The invariant gate remains authoritative; this convenience tool cannot waive it.

`python3 scripts/test_task_inputs.py` exercises stale helper and inventory changes, symlinked and
oversized inputs, unknown contracts, and the output and time bounds of the process runner;
`python3 scripts/test_proof_task.py` and `python3 scripts/test_sokol_dev.py` the proof challenge
and the entry point. Linux unit witnesses are separate runtime checks; mocked test output in these
regressions is not native execution evidence.
