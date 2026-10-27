# GAPS: what Warrant 3 cannot express of what sokol-core's machinery enforces

Companion of [README.md](README.md) (phase 1 of the Warrant 3 study, source `dad26967`). Warrant
side: `warrant-graph` 3.0.0a1, its spec `docs/V3.md` and the repository tools of s0fractal/warrant
at `55824eed` (`tools/claims.py`, `tools/review.py`, `tools/gate.py`, the review waker). Each gap
says what sokol enforces, what Warrant 3 has, what would be lost by switching, and who should
carry the piece: warrant (a proposal W-n, not made in this task) or sokol (it keeps its own).

Summary: the record layer has no gap (README: verify IDENTICAL). G1-G4 are the costly machinery and
stay sokol's; G5-G6 are what phase 2 needs from warrant; G7-G10 are small and need no warrant change;
G11 answers the owner's question: which of the owner's acts a store could count by itself.

| gap | sokol keeps | warrant proposal |
| --- | --- | --- |
| G1 witness-body pins | yes | W-1 protected lineages in the gate (optional) |
| G2 Rust/cargo witnesses and mutants | yes | W-2 a declared test runner for the claims and review tools |
| G3 base-pinned witness gate | yes | none: different job; W-3 is only a binding note |
| G4 owner SSH signature over a manifest | yes | W-4 an SSHSIG basis for attests |
| G5 waker hard-codes the repository | — | W-5 repository and branch from configuration |
| G6 review loop and gate are not in the wheel | — | W-6 package them, or vendor by exact commit |
| G7 annotations bound into the version id | mapping choice | none |
| G8 one shared agent key | sokol's decision | none |
| G9 time and order from Git | as today | none |
| G10 the document around the rows | yes | none |
| G11 the owner's acts as a count from the store | partly | W-7 an act ledger view; W-8 forge acts as observations |

## G1. Witness-body pins vs Warrant's whole-tree identity

**Sokol enforces** (ADR-0023, `scripts/witness-pin.py`): the owner's manifest pins every cited
test's body (Rust tokens with comments and layout stripped; Python AST), its closure (attributes
and the test items and helpers it reaches: closures_v4), the build inputs that decide how tests
are built and run (Cargo target sections, `.cargo/config`, `build.rs`, the toolchain file: build_v3)
and the trust root (signers, the checker, the gate workflow, the Python arguments CI passes:
trust_root_v2). A pull request that changes a pinned body without a new owner signature fails the
gate: a cited test cannot be weakened under its old name.

**Warrant 3 has**: a version's id covers its witnesses' *names*. The claims checker's acceptance
names the commit, its tree, the checker's code and env; acceptance holds for its commit, and the
claims view says whether a claim's acceptance is at the current tree. Any byte change makes it
"not at this tree"; nothing refuses a weakened test, and re-acceptance is mechanical.

**Lost by switching**: the ADR-0023 guarantee itself. The mirror carries each manifest only as its
sha256 in the acceptance (README R4).

**Verdict: sokol keeps** `scripts/witness-pin.py`'s extraction (480 lines of Rust/Python-specific
parsing; domain code, not a record rule). It can be expressed over Warrant 3 without a core
change: put the witness digests into the contract version's body (so its id covers them) and let a
sokol checker actor (named by the digest of `scripts/witness-pin.py`, V3 §6) attest at each head
that they still hold, or file a challenge when one moved. **W-1** (optional, `tools/gate.py`): a
merge rule over *protected lineages* — a counted challenge standing against any lineage the base's
configuration names refuses the merge — so such a challenge blocks as the witness gate does today.
The gate's `OPEN_FINDING` does this only for the pull request's own head lineage.

## G2. Cargo witnesses and mutants vs the claims checker's Python runner

**Sokol enforces**: witnesses are `cargo test` cases (Linux only: aya, the eBPF object), Kani
proofs and Python unittest cases; the gate requires that every pinned witness ran and passed in
CI (`witness-pin.py` reads cargo's `test NAME ... ok` lines); mutants are cargo-mutants over the
changed lines (`scripts/mutants-diff.sh`).

**Warrant 3 has**: `tools/claims.py` runs `python -B tests/<file>` and reads `ok   CASE` lines;
mutants are `tests/mutants.py` find/replace rows; the review replayer runs a finding's test as one
new file under `tests/`. All Python, all on the checker's host.

**Lost by switching**: every replay. The claims checker cannot run one sokol witness, and a sokol
finding with a Rust test would be an unreplayed thesis.

**Verdict: sokol keeps** its runners. Warrant 3's checker rule (V3 §6) already admits any program
under a stable actor id with `code` and `env`, so a sokol runner can attest in Warrant records
without warrant changing. **W-2**: give `tools/claims.py` and `tools/review.py` a declared runner
in the repository configuration (a command per witness kind and the line pattern that says
passed/failed, cargo's included) instead of a hard-coded Python one; without it phase 2's findings
are verdicts without replay (README stop criteria).

## G3. The base-pinned witness gate vs merge on acceptance

**Sokol enforces** (`.github/workflows/witness-gate.yml`, ADR-0023, ADR-0030): a required check on
`pull_request_target` that runs main's checker with main's signers against the pull request's tree,
fails on pin drift without the owner's signature and on a pinned witness that did not run and pass.
It never merges; the owner merges (60 of 60 in the window).

**Warrant 3 has** (`tools/gate.py`, `docs/V3.md` §14): the same trust discipline — base code, base
configuration, the head read as Git objects — with another predicate: a head version accepted by a
`pr/acceptor`, no standing finding, only allowed tail changes, no owner path changed, required
checks bound to their workflow files; then it merges with the workflow's token.

**Lost by switching**: all pin checks (G1). They are complementary, not alternatives.

**Verdict: sokol keeps** the witness gate as a required check. **W-3** is a note, not a feature:
when sokol later adopts merge on acceptance, the witness gate goes into `.warrant/merge.json`'s
`required` list bound to its workflow file, and the gate's owner paths include the witness gate,
the signers and the manifests.

## G4. The owner's SSH signature over a manifest vs owner paths

**Sokol enforces**: the owner's act is one `ssh-keygen -Y sign` (namespace `sokol-witness`) over
the whole manifest, verified against `.github/witness-signers` taken from the base; rotating the
signers is itself pinned (trust_root_v2). The signature binds the owner to exact bytes and can be
checked offline, forever. The agent tier is the same with the `agent` principal (ADR-0028).

**Warrant 3 has**: actors with Ed25519 keys in the trust (signature over `warrant-sig-v3:` and the
record id), and in warrant's own repository `owner_paths`: files whose change the gate refuses to
merge, so the owner merges them by hand — a forge act, observed, not signed.

**Lost by switching to owner paths**: the cryptographic binding of the owner to what was accepted;
a merge click binds a head, not pins, and cannot be re-verified from the store. In the mirror the
owner's signatures could only become MIGRATED acceptances (README R5): the store says a
signature verified, the replay from Git re-checks it.

**Verdict: sokol keeps** the manifest signature. **W-4**: an SSHSIG basis for attests — a trust
key typed `ssh-ed25519` with a namespace, and an attest whose signature is an OpenSSH SSHSIG over
the record id (or over a blob that lists record ids). The owner's existing tool would then produce
SIGNED Warrant acceptances, one signing act per batch as today (34 re-signs in the window). Without
W-4 the alternative is a Warrant key for the owner and a batch `attest` command — the same number of
owner acts, but a new tool in the owner's hands.

## G5. The review waker hard-codes its repository

`integrations/codex-plugin/waker/waker.py` at `55824eed` line 99: `REPO = "s0fractal/warrant"`,
`BRANCH = "master"`, `OPERATOR_CHECKOUT = ~/Projects/warrant`, and the checker paths of warrant's
tree. Sokol's branch is `main`. **Lost**: no reviewer is woken for a sokol pull request; phase 2
would need a manual start for every head. **W-5**: the waker reads the repositories it serves
(repository, base branch, operator checkout) from its own configuration and refuses a base whose
`.warrant/v3.json` names another repository. Precondition of phase 2.

## G6. The review loop and the gate are repository tools, not the package

The `warrant-graph` 3.0.0a1 wheel holds `warrant/` and `warrant_agent/`. `tools/review.py`,
`tools/gate.py`, `tools/claims.py` and `tools/repo.py` live only in warrant's tree, and their
checker identities are digests of that tree. **Lost**: sokol cannot install the review loop; a copy
would drift and its identity would name code warrant never reviewed. **W-6**: package the loop
(review, gate, the repository config reader) as an installable, versioned module, or document
vendoring at an exact warrant commit with the identity it then has. Precondition of phase 2.

## G7. Annotations are inside the version

Sokol's contract annotations are unsigned explanations: `contract_pins` leaves them out, and they
can change without a new signature. A Warrant version's id covers its whole body, so an annotation
edit would be a new version waiting for a new acceptance. Measured: no contract's annotations ever
changed apart from a decision (100 commits, 100 versions). **Verdict**: no warrant change; if it
matters, carry annotations as their own unguarded lineage that names the contract's root.

## G8. One shared agent key

ADR-0028's provisional tier has one `agent` principal for every agent. Warrant binds keys per
actor and grants roles in the receiver's profile (in warrant: `claude`, `codex`). Nothing is lost;
per-agent attribution is gained if sokol wants it. Sokol's decision.

## G9. Time and order come from Git

A migrated version's `at` is its commit's committer time, which nobody signed, and migrated
records are in no actor chain (V3 §7): the order is witnessed by Git history, as in warrant's own
v2 migration. Sokol has no signed time either; nothing is lost against today.

## G10. The document around the rows

INVARIANTS.md's prose and row order (`scripts/contract.py propose` places a new row after an
existing one) are the document's, not the contracts' (README R2). Warrant's views generate whole
documents; sokol's renderer, which keeps hand-written prose between generated rows, stays.

## G11. Would Warrant records make the owner's act count derivable from the store?

**Today** (README, phase 0) the count needs three sources and a policy: the owner's SSH signatures
in Git (KEY), Git itself (REPO), and GitHub's API (FORGE), where every pull request, comment and
merge carries the owner's login because the agents use the owner's token. GitHub's actor field
cannot tell the owner from an agent; only the owner's key and the stated policy do.

**With every governance act a record** — the actor on every act, signed by that actor's own key
(V3 §2, §7) — the store answers by itself, as a count of records by actor per week:

- contract acceptances and promotes: an `attest` by the owner on each version it accepts;
- reviews, verdicts and findings (phase 2): a `pr-head@1` version per head, an accept or a
  challenge by the reviewer's own key (`codex`, `claude`, or the owner when the owner reviews);
- agents' acts under their own keys: the "unattributed" problem goes away for every act that is a
  record (not for code commits, which stay Git's);
- order per actor from its chain, so a backdated act is visible (V3 §7).

**The unit changes.** The mirror shows it: sokol's owner signs whole manifests, Warrant accepts
versions. The 34 re-signs became 94 owner acceptances, from 23 of the 34 signing commits; the
other 11 re-signs pinned no new contract version (witness bodies, closures, build inputs, the trust
root: G1) and do not appear in the store at all. A store-derived count is in acceptances of
versions; one owner session that signs a batch is several records (the chain orders them, nothing
groups them). Counting sessions needs a batch marker, or one attest over a blob that lists ids (W-4).

**What stays outside the store:**

- the forge's acts: merges by a person, rulesets, repository settings, "Update branch", re-runs,
  secrets. A merge can be *observed* by a record (warrant's gate does: a merge observation naming
  the merge commit), but the observation does not say who clicked;
- trust and profile changes: the keys and roles are a file (`.warrant/v3.json`) changed by a
  merged pull request, a Git and forge act, not a record;
- key creation and custody: a record signed by the owner's key proves the key, not the hand;
- decisions in conversation, and the owner's reading;
- completeness: a store is `UNATTESTED` complete (V3 §10). It counts the acts that were recorded;
  it cannot prove no other act happened. The count becomes a full count only where the gate refuses
  what has no record (a merge without an accepted head, a contract change without an acceptance).

**Proposals.** **W-7**: an act ledger view in warrant — records per actor per week, split SIGNED /
MIGRATED, with each record's kind and schema — so the README's trend table is a generated view of
the store instead of a script over three sources. **W-8**: forge acts as observations — the gate
(or an observer checker named by its code) files an `attest` for each merge, ruleset version and
re-run it can read from the API, with the actor GitHub reports, labelled as observed, never signed by
that actor. And outside Warrant, for sokol: agents get their own GitHub identity (an app or a bot
account) instead of the owner's token; that alone splits the FORGE class into the owner's and the
agents' acts, and it is the second login ADR-0032 is waiting for.

## What Warrant 3 carries that sokol's machinery does not

- **Proposals are kept.** A Warrant proposal is a filed version waiting for its guard while the
  earlier version stays effective; `scripts/contract.py accept` deletes the proposal file, and 6 of
  67 proposals are gone from Git (README R3).
- **Acceptance per version is a record.** Who accepted which version, from which signed manifest,
  is queryable: 100 acceptances from 27 signing commits. In sokol it is implicit in the manifest
  history.
- **Concurrent changes are a FORK**, listed with both branches; sokol refuses a stale proposal by
  its base hash, which keeps the second change out instead of showing it.
